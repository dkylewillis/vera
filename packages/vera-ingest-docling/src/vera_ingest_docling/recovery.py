"""Page-level recovery, whole-document pypdfium2, and batched pypdfium2 fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, NoReturn

from vera_ingest.cancellation import raise_if_cancelled
from vera_ingest.types import IngestBlock, IngestChunk, ParsedPage

from . import converter as _converter
from .mapping import _chunk_document, map_docling_document
from .options import DoclingOptions, is_pdf_source

# Above this ratio of failed pages, skip per-page recovery and reconvert the
# whole document once with pypdfium2 (avoids paying model-init per page).
_MAX_RECOVERABLE_PAGE_RATIO = 0.2

# When whole-document pypdfium2 still raises (typical OOM on large manuals),
# reconvert this many pages at a time with one reused converter.
_FALLBACK_BATCH_PAGES = 8

# Docling 2.118 ErrorItem has no page_no; StandardPdfPipeline records
# ``Page {page.page_no} failed to parse.`` with 0-based Page.page_no.
_PAGE_FAILED_RE = re.compile(r"(?i)\bpage\s+(\d+)\s+failed")


@dataclass
class _MappedConversion:
    """Mapped/chunked output from a successful Docling conversion."""

    pages: list[ParsedPage]
    blocks: list[IngestBlock]
    chunks: list[IngestChunk]
    backend: str
    whole_fallback: str | None = None
    fallback_strategy: str | None = None


def _is_memory_error_blob(blob: str) -> bool:
    """Return True when the error text looks like a Docling native OOM."""
    lowered = (blob or "").lower()
    return "bad_alloc" in lowered or "out of memory" in lowered or "memoryerror" in lowered


def _format_docling_errors(result: Any) -> str:
    errors = getattr(result, "errors", None) or []
    messages: list[str] = []
    for entry in errors:
        text = str(getattr(entry, "error_message", None) or entry).strip()
        if text and text not in messages:
            messages.append(text)
    if not messages:
        return ""
    joined = " | ".join(messages[:5])
    if len(messages) > 5:
        joined = f"{joined} | …(+{len(messages) - 5} more)"
    hints: list[str] = []
    blob = " ".join(messages).lower()
    if "compiler: cl is not found" in blob or "torchdynamo" in blob:
        hints.append(
            "Torch compile/Inductor needs MSVC cl.exe on Windows; "
            "VERA disables torch.compile for Docling — restart the app after updating."
        )
    if _is_memory_error_blob(blob):
        hints.append(
            "Docling ran out of memory; VERA retries failed pages then falls back "
            "to the pypdfium2 backend. Force it with --pipeline-option pdf_backend=pypdfium2."
        )
    if hints:
        return f"{joined} Hint: {' '.join(hints)}"
    return joined


def _page_from_error_message(text: str) -> int | None:
    """Parse a 1-based page number from a Docling ``Page N failed…`` message."""
    match = _PAGE_FAILED_RE.search(text or "")
    if match is None:
        return None
    # Page.page_no in the stock message is 0-based; VERA pages are 1-based.
    return int(match.group(1)) + 1


def _page_from_error_entry(entry: Any) -> int | None:
    text = str(getattr(entry, "error_message", None) or "")
    parsed = _page_from_error_message(text)
    if parsed is not None:
        return parsed
    page_no = getattr(entry, "page_no", None)
    if page_no is None:
        return None
    try:
        page_int = int(page_no)
    except (TypeError, ValueError):
        return None
    if page_int >= 0:
        # 0-based leftover; anything >0 is treated as already 1-based.
        return page_int + 1 if page_int == 0 else page_int
    return None


def _missing_pages_from_counts(result: Any) -> list[int]:
    """Infer failed 1-based pages by diffing input page_count vs assembled pages."""
    input_doc = getattr(result, "input", None)
    page_count = getattr(input_doc, "page_count", None)
    if not isinstance(page_count, int) or page_count <= 0:
        return []
    expected = set(range(1, page_count + 1))
    present: set[int] = set()
    document = getattr(result, "document", None)
    if document is not None:
        pages = getattr(document, "pages", None) or {}
        present.update(int(page) for page in pages)
    conv_pages = getattr(result, "pages", None) or []
    for page in conv_pages:
        page_no = getattr(page, "page_no", None)
        if page_no is None:
            continue
        try:
            raw = int(page_no)
        except (TypeError, ValueError):
            continue
        # ConversionResult.pages use 0-based Page.page_no.
        present.add(raw + 1 if raw >= 0 else raw)
    return sorted(expected - present)


def _failed_page_numbers(result: Any) -> list[int]:
    """Return distinct sorted 1-indexed page numbers from Docling errors."""
    pages: set[int] = set()
    for entry in getattr(result, "errors", None) or []:
        parsed = _page_from_error_entry(entry)
        if parsed is not None:
            pages.add(parsed)
    if not pages:
        pages.update(_missing_pages_from_counts(result))
    return sorted(pages)


def _result_has_memory_errors(result: Any) -> bool:
    errors = getattr(result, "errors", None) or []
    for entry in errors:
        text = str(getattr(entry, "error_message", None) or entry)
        if _is_memory_error_blob(text):
            return True
    return False


def _assert_conversion_ok(result: Any) -> Any:
    from docling.datamodel.base_models import ConversionStatus

    status = getattr(result, "status", None)
    if status is None:
        raise ValueError("Docling conversion returned no status.")
    if status == ConversionStatus.SUCCESS:
        document = getattr(result, "document", None)
        if document is None:
            raise ValueError("Docling conversion succeeded but returned no document.")
        return document
    status_name = getattr(status, "name", str(status))
    detail = _format_docling_errors(result)
    suffix = f" Errors: {detail}" if detail else ""
    raise ValueError(
        f"Docling conversion did not fully succeed (status={status_name}). "
        f"Partial or failed results are rejected when recovery is exhausted.{suffix}"
    )


def _mapped_from_success(
    result: Any,
    config: DoclingOptions,
    *,
    backend: str,
) -> _MappedConversion | None:
    """Map a SUCCESS ConversionResult; return None if status is not SUCCESS."""
    from docling.datamodel.base_models import ConversionStatus

    if getattr(result, "status", None) != ConversionStatus.SUCCESS:
        return None
    document = getattr(result, "document", None)
    if document is None:
        return None
    pages, blocks = map_docling_document(document)
    chunks = _chunk_document(document, blocks, config)
    return _MappedConversion(pages=pages, blocks=blocks, chunks=chunks, backend=backend)


def _convert_single_page(
    source_path: str,
    page_no: int,
    config: DoclingOptions,
    backend: str,
) -> _MappedConversion | None:
    """Convert one page with a fresh converter; return mapped output or None."""
    result, _error = _converter._try_convert(
        source_path,
        config,
        backend=backend,
        page_range=(page_no, page_no),
    )
    if result is None:
        return None
    return _mapped_from_success(result, config, backend=backend)


def _unique_block_id(block_id: str, seen: set[str]) -> str:
    if block_id not in seen:
        seen.add(block_id)
        return block_id
    suffix = 2
    while f"{block_id}_{suffix}" in seen:
        suffix += 1
    unique = f"{block_id}_{suffix}"
    seen.add(unique)
    return unique


def _chunk_overlaps_pages(chunk: IngestChunk, pages: set[int]) -> bool:
    """Return True when the chunk's inclusive page range overlaps ``pages``."""
    if not pages:
        return False
    return any(chunk.page_start <= page <= chunk.page_end for page in pages)


def _merge_recovered_page(
    pages: list[ParsedPage],
    blocks: list[IngestBlock],
    chunks: list[IngestChunk],
    page_no: int,
    recovered: _MappedConversion,
) -> tuple[list[ParsedPage], list[IngestBlock], list[IngestChunk]]:
    """Replace/append content for ``page_no`` with a recovered page's mapped output."""
    # Drop any residual content that Docling left for the failed page.
    pages = [page for page in pages if page.page_number != page_no]
    blocks = [block for block in blocks if block.page_number != page_no]
    chunks = [chunk for chunk in chunks if not _chunk_overlaps_pages(chunk, {page_no})]

    recovered_pages = [page for page in recovered.pages if page.page_number == page_no]
    if not recovered_pages and recovered.pages:
        # Single-page convert sometimes labels the only page as 1; re-tag.
        recovered_pages = [
            ParsedPage(
                page_number=page_no,
                width=page.width,
                height=page.height,
                text=page.text,
            )
            for page in recovered.pages
        ]
    pages.extend(recovered_pages)
    pages.sort(key=lambda page: page.page_number)

    seen_ids = {block.block_id for block in blocks}
    remapped_ids: dict[str, str] = {}
    for block in recovered.blocks:
        # Re-tag page number if the single-page convert used page 1.
        page_number = page_no if len(recovered.pages) == 1 else block.page_number
        if page_number != page_no and block.page_number != page_no:
            continue
        new_id = _unique_block_id(block.block_id, seen_ids)
        remapped_ids[block.block_id] = new_id
        regions = list(block.regions or [])
        if page_number != block.page_number:
            regions = [
                {**region, "page_number": page_number} if isinstance(region, dict) else region
                for region in regions
            ]
        blocks.append(
            replace(
                block,
                block_id=new_id,
                page_number=page_number,
                regions=regions,
            )
        )

    next_index = len(chunks) + 1
    for chunk in recovered.chunks:
        page_start = page_no if len(recovered.pages) == 1 else chunk.page_start
        page_end = page_no if len(recovered.pages) == 1 else chunk.page_end
        if page_start != page_no and chunk.page_start != page_no:
            continue
        new_block_ids = [remapped_ids.get(bid, bid) for bid in chunk.block_ids]
        chunks.append(
            replace(
                chunk,
                chunk_id=f"chunk_{next_index:06d}",
                page_start=page_start,
                page_end=page_end,
                block_ids=new_block_ids,
                metadata={
                    **dict(chunk.metadata or {}),
                    "recovered_page": True,
                    "recovery_backend": recovered.backend,
                },
            )
        )
        next_index += 1

    chunks.sort(key=lambda chunk: (chunk.page_start, chunk.chunk_id))
    return pages, blocks, chunks


def _page_count_estimate(result: Any, failed_pages: list[int]) -> int:
    input_doc = getattr(result, "input", None)
    page_count = getattr(input_doc, "page_count", None)
    if isinstance(page_count, int) and page_count > 0:
        return page_count
    document = getattr(result, "document", None)
    if document is not None:
        pages = getattr(document, "pages", None) or {}
        if pages:
            try:
                highest = max(int(page) for page in pages)
            except (TypeError, ValueError):
                highest = len(pages)
            return max(highest, max(failed_pages, default=0), len(pages))
    return max(failed_pages, default=1)


def _raise_from(message: str, cause: BaseException | None) -> NoReturn:
    if cause is None:
        raise ValueError(message)
    raise ValueError(message) from cause


def _format_exceptions(errors: list[BaseException]) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for exc in errors:
        text = f"{type(exc).__name__}: {exc}".strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(text)
    if not unique:
        return ""
    joined = " | ".join(unique[:3])
    if len(unique) > 3:
        joined = f"{joined} | …(+{len(unique) - 3} more)"
    return joined


def _pdf_page_count(source_path: str) -> int | None:
    """Return the PDF page count, or None if the file cannot be opened."""
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(source_path)
        try:
            count = len(document)
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()
    except Exception:  # noqa: BLE001 - missing/corrupt PDFs should not crash recovery
        return None
    return count if isinstance(count, int) and count > 0 else None


def _shift_mapped(mapped: _MappedConversion, offset: int) -> _MappedConversion:
    if offset == 0:
        return mapped
    pages = [
        ParsedPage(
            page_number=page.page_number + offset,
            width=page.width,
            height=page.height,
            text=page.text,
        )
        for page in mapped.pages
    ]
    blocks = []
    for block in mapped.blocks:
        page_number = block.page_number + offset
        regions = list(block.regions or [])
        shifted_regions = []
        for region in regions:
            if isinstance(region, dict) and "page_number" in region:
                shifted = dict(region)
                try:
                    shifted["page_number"] = int(shifted["page_number"]) + offset
                except (TypeError, ValueError):
                    pass
                shifted_regions.append(shifted)
            else:
                shifted_regions.append(region)
        blocks.append(
            replace(
                block,
                page_number=page_number,
                regions=shifted_regions if regions else block.regions,
            )
        )
    chunks = [
        replace(
            chunk,
            page_start=chunk.page_start + offset,
            page_end=chunk.page_end + offset,
        )
        for chunk in mapped.chunks
    ]
    return replace(mapped, pages=pages, blocks=blocks, chunks=chunks)


def _retarget_mapped(mapped: _MappedConversion, start: int, end: int) -> _MappedConversion:
    """Relabel a page-range convert onto the original 1-based PDF pages."""
    if end < start:
        return mapped
    numbers = sorted({page.page_number for page in mapped.pages})
    if not numbers or numbers[0] == start:
        return mapped
    return _shift_mapped(mapped, start - numbers[0])


def _append_mapped(base: _MappedConversion, incoming: _MappedConversion) -> _MappedConversion:
    """Concatenate a later batch onto an accumulated mapped conversion."""
    incoming_pages = {page.page_number for page in incoming.pages}
    pages = [page for page in base.pages if page.page_number not in incoming_pages]
    pages.extend(incoming.pages)
    pages.sort(key=lambda page: page.page_number)

    blocks = [block for block in base.blocks if block.page_number not in incoming_pages]
    seen_ids = {block.block_id for block in blocks}
    remapped_ids: dict[str, str] = {}
    for block in incoming.blocks:
        new_id = _unique_block_id(block.block_id, seen_ids)
        remapped_ids[block.block_id] = new_id
        blocks.append(block if new_id == block.block_id else replace(block, block_id=new_id))

    chunks = [chunk for chunk in base.chunks if not _chunk_overlaps_pages(chunk, incoming_pages)]
    next_index = len(chunks) + 1
    for chunk in incoming.chunks:
        chunks.append(
            replace(
                chunk,
                chunk_id=f"chunk_{next_index:06d}",
                block_ids=[remapped_ids.get(block_id, block_id) for block_id in chunk.block_ids],
            )
        )
        next_index += 1
    chunks.sort(key=lambda chunk: (chunk.page_start, chunk.chunk_id))
    return replace(base, pages=pages, blocks=blocks, chunks=chunks)


def _convert_page_range(
    source_path: str,
    config: DoclingOptions,
    *,
    start: int,
    end: int,
    converter: Any,
) -> tuple[_MappedConversion | None, BaseException | None]:
    result, error = _converter._try_convert(
        source_path,
        config,
        backend=_converter._PDF_BACKEND_PYPDFIUM2,
        page_range=(start, end),
        converter=converter,
    )
    if result is None:
        return None, error
    mapped = _mapped_from_success(result, config, backend=_converter._PDF_BACKEND_PYPDFIUM2)
    if mapped is None:
        return None, error
    return _retarget_mapped(mapped, start, end), error


def _batched_pypdfium2_convert(
    *,
    source_path: str,
    config: DoclingOptions,
    cancel: Any | None,
) -> tuple[_MappedConversion | None, list[BaseException]]:
    """Convert the PDF in page windows so peak memory stays bounded."""
    errors: list[BaseException] = []
    page_count = _pdf_page_count(source_path)
    if page_count is None:
        return None, errors
    try:
        converter = _converter._build_converter(config, backend=_converter._PDF_BACKEND_PYPDFIUM2)
    except Exception as exc:  # noqa: BLE001
        if _converter._is_cancellation(exc):
            raise
        _converter._log_convert_failure(_converter._PDF_BACKEND_PYPDFIUM2, None, exc)
        return None, [exc]

    accumulated: _MappedConversion | None = None
    page = 1
    while page <= page_count:
        raise_if_cancelled(cancel)
        end = min(page + _FALLBACK_BATCH_PAGES - 1, page_count)
        mapped, error = _convert_page_range(
            source_path, config, start=page, end=end, converter=converter
        )
        if error is not None:
            errors.append(error)
        if mapped is None and end > page:
            for page_no in range(page, end + 1):
                raise_if_cancelled(cancel)
                page_mapped, page_error = _convert_page_range(
                    source_path,
                    config,
                    start=page_no,
                    end=page_no,
                    converter=converter,
                )
                if page_error is not None:
                    errors.append(page_error)
                if page_mapped is None:
                    return None, errors
                accumulated = (
                    page_mapped if accumulated is None else _append_mapped(accumulated, page_mapped)
                )
            page = end + 1
            continue
        if mapped is None:
            return None, errors
        accumulated = mapped if accumulated is None else _append_mapped(accumulated, mapped)
        page = end + 1
    return accumulated, errors


def _whole_document_pypdfium2_fallback(
    *,
    source_path: str,
    config: DoclingOptions,
    cancel: Any | None,
    prior: Any | None,
    cause: BaseException | None = None,
) -> _MappedConversion:
    raise_if_cancelled(cancel)
    errors: list[BaseException] = []
    if cause is not None:
        errors.append(cause)

    if config.pdf_backend != _converter._PDF_BACKEND_PYPDFIUM2:
        result, error = _converter._try_convert(
            source_path,
            config,
            backend=_converter._PDF_BACKEND_PYPDFIUM2,
        )
        if error is not None:
            errors.append(error)
        if result is not None:
            mapped = _mapped_from_success(result, config, backend=_converter._PDF_BACKEND_PYPDFIUM2)
            if mapped is not None:
                return replace(
                    mapped,
                    whole_fallback=_converter._PDF_BACKEND_PYPDFIUM2,
                    fallback_strategy="document",
                )

    mapped, batch_errors = _batched_pypdfium2_convert(
        source_path=source_path,
        config=config,
        cancel=cancel,
    )
    errors.extend(batch_errors)
    if mapped is not None:
        return replace(
            mapped,
            whole_fallback=_converter._PDF_BACKEND_PYPDFIUM2,
            fallback_strategy="batched",
        )

    detail = _format_exceptions(errors)
    suffix = f" Cause: {detail}" if detail else ""
    if prior is not None:
        try:
            _assert_conversion_ok(prior)
        except ValueError as exc:
            message = str(exc)
            if suffix and suffix[8:] not in message:
                message = f"{message}{suffix}"
            _raise_from(message, cause)
    _raise_from(
        "Docling conversion failed and the pypdfium2 whole-document fallback also failed." + suffix,
        cause,
    )


def _recover_page(
    source_path: str,
    page_no: int,
    config: DoclingOptions,
) -> tuple[_MappedConversion | None, str]:
    """Retry one page; skip docling_parse when the user forced pypdfium2."""
    if config.pdf_backend != _converter._PDF_BACKEND_PYPDFIUM2:
        recovered = _convert_single_page(
            source_path,
            page_no,
            config,
            _converter._PDF_BACKEND_DOCLING_PARSE,
        )
        if recovered is not None:
            return recovered, _converter._PDF_BACKEND_DOCLING_PARSE
    recovered = _convert_single_page(
        source_path,
        page_no,
        config,
        _converter._PDF_BACKEND_PYPDFIUM2,
    )
    return recovered, _converter._PDF_BACKEND_PYPDFIUM2


def _resolve_conversion(
    *,
    source_path: str,
    config: DoclingOptions,
    conversion: Any | None,
    primary_backend: str,
    primary_raised: bool,
    cancel: Any | None,
    recovered_pages: list[int],
    recovered_pages_backend: dict[int, str],
    primary_error: BaseException | None = None,
) -> _MappedConversion:
    from docling.datamodel.base_models import ConversionStatus

    if not is_pdf_source(source_path):
        if conversion is not None:
            mapped = _mapped_from_success(conversion, config, backend=primary_backend)
            if mapped is not None:
                return mapped
        if conversion is None:
            _raise_from("Docling conversion failed.", primary_error)
        status = getattr(conversion, "status", None)
        status_name = getattr(status, "name", str(status))
        detail = _format_docling_errors(conversion)
        suffix = f" Errors: {detail}" if detail else ""
        _raise_from(
            f"Docling conversion did not fully succeed (status={status_name}).{suffix}",
            primary_error,
        )

    # Fast path: clean SUCCESS on the primary backend.
    if conversion is not None and getattr(conversion, "status", None) == ConversionStatus.SUCCESS:
        mapped = _mapped_from_success(conversion, config, backend=primary_backend)
        if mapped is not None:
            return mapped

    failed_pages: list[int] = _failed_page_numbers(conversion) if conversion is not None else []
    has_memory = conversion is not None and _result_has_memory_errors(conversion)
    status = getattr(conversion, "status", None) if conversion is not None else None
    can_recover = status == ConversionStatus.PARTIAL_SUCCESS and bool(failed_pages) and has_memory

    need_whole_fallback = primary_raised
    if has_memory and not can_recover:
        # Memory errors with no attributable pages (typical real ErrorItem)
        # must fall back to whole-document pypdfium2 instead of rejecting.
        need_whole_fallback = True
    if status == ConversionStatus.FAILURE:
        # Invalid input / missing docling-parse resources (no exception, 0 pages).
        need_whole_fallback = True
    if can_recover:
        total_pages = _page_count_estimate(conversion, failed_pages)
        ratio = len(failed_pages) / max(total_pages, 1)
        if ratio > _MAX_RECOVERABLE_PAGE_RATIO:
            need_whole_fallback = True

    if need_whole_fallback:
        return _whole_document_pypdfium2_fallback(
            source_path=source_path,
            config=config,
            cancel=cancel,
            prior=conversion,
            cause=primary_error,
        )

    if not can_recover:
        # Document-scoped / non-memory partial failures keep today's reject path.
        if conversion is None:
            _raise_from(
                "Docling conversion failed and recovery could not obtain a result.",
                primary_error,
            )
        _assert_conversion_ok(conversion)
        raise AssertionError("unreachable")  # pragma: no cover

    # Per-page recovery on the partial document.
    assert conversion is not None
    document = getattr(conversion, "document", None)
    if document is None:
        return _whole_document_pypdfium2_fallback(
            source_path=source_path,
            config=config,
            cancel=cancel,
            prior=conversion,
            cause=primary_error,
        )

    pages, blocks = map_docling_document(document)
    failed_set = set(failed_pages)
    all_chunks = _chunk_document(document, blocks, config)
    chunks = [chunk for chunk in all_chunks if not _chunk_overlaps_pages(chunk, failed_set)]
    # Also drop blocks/pages for failed pages so recovered content replaces them.
    pages = [page for page in pages if page.page_number not in failed_set]
    blocks = [block for block in blocks if block.page_number not in failed_set]

    unrecoverable: list[int] = []
    for page_no in failed_pages:
        raise_if_cancelled(cancel)
        recovered, backend_used = _recover_page(source_path, page_no, config)
        if recovered is None:
            unrecoverable.append(page_no)
            continue
        pages, blocks, chunks = _merge_recovered_page(pages, blocks, chunks, page_no, recovered)
        recovered_pages.append(page_no)
        recovered_pages_backend[page_no] = backend_used

    if unrecoverable:
        detail = _format_docling_errors(conversion)
        pages_text = ", ".join(str(p) for p in unrecoverable)
        suffix = f" Errors: {detail}" if detail else ""
        raise ValueError(
            f"Docling conversion did not fully succeed "
            f"(unrecoverable pages: {pages_text}). "
            f"Partial or failed results are rejected when recovery is exhausted.{suffix}"
        )

    return _MappedConversion(
        pages=pages,
        blocks=blocks,
        chunks=chunks,
        backend=primary_backend,
    )
