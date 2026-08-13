"""Page-level recovery and whole-document pypdfium2 fallback."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from vera_ingest.types import IngestBlock, IngestChunk, ParsedPage

from . import converter as _converter
from .mapping import _chunk_document, map_docling_document
from .options import DoclingOptions

# Above this ratio of failed pages, skip per-page recovery and reconvert the
# whole document once with pypdfium2 (avoids paying model-init per page).
_MAX_RECOVERABLE_PAGE_RATIO = 0.2


@dataclass
class _MappedConversion:
    """Mapped/chunked output from a successful Docling conversion."""

    pages: list[ParsedPage]
    blocks: list[IngestBlock]
    chunks: list[IngestChunk]
    backend: str
    whole_fallback: str | None = None


def _raise_if_cancelled(cancel: Any | None) -> None:
    if cancel is None:
        return
    interrupted = getattr(cancel, "raise_if_interrupted", None)
    if callable(interrupted):
        interrupted()
        return
    cancelled = getattr(cancel, "raise_if_cancelled", None)
    if callable(cancelled):
        cancelled()


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


def _failed_page_numbers(result: Any) -> list[int]:
    """Return distinct sorted 1-indexed page numbers from Docling ErrorItems."""
    pages: set[int] = set()
    for entry in getattr(result, "errors", None) or []:
        page_no = getattr(entry, "page_no", None)
        if page_no is None:
            continue
        try:
            page_int = int(page_no)
        except (TypeError, ValueError):
            continue
        if page_int > 0:
            pages.add(page_int)
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
    result = _converter._try_convert(
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
    chunks = [
        chunk
        for chunk in chunks
        if not (chunk.page_start == page_no and chunk.page_end == page_no)
    ]

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
    document = getattr(result, "document", None)
    if document is not None:
        pages = getattr(document, "pages", None) or {}
        if pages:
            return max(len(pages), max(failed_pages, default=0))
    return max(failed_pages, default=1)


def _whole_document_pypdfium2_fallback(
    *,
    source_path: str,
    config: DoclingOptions,
    cancel: Any | None,
    prior: Any | None,
) -> _MappedConversion:
    _raise_if_cancelled(cancel)
    if config.pdf_backend == _converter._PDF_BACKEND_PYPDFIUM2:
        # Already on pypdfium2; nothing left to try.
        if prior is not None:
            _assert_conversion_ok(prior)
        raise ValueError(
            "Docling conversion failed with pdf_backend=pypdfium2; "
            "no further backend fallback is available."
        )
    result = _converter._try_convert(
        source_path,
        config,
        backend=_converter._PDF_BACKEND_PYPDFIUM2,
    )
    if result is None:
        if prior is not None:
            _assert_conversion_ok(prior)
        raise ValueError(
            "Docling conversion failed and the pypdfium2 whole-document "
            "fallback also failed."
        )
    mapped = _mapped_from_success(result, config, backend=_converter._PDF_BACKEND_PYPDFIUM2)
    if mapped is None:
        _assert_conversion_ok(result)
        raise AssertionError("unreachable")  # pragma: no cover
    return replace(mapped, whole_fallback=_converter._PDF_BACKEND_PYPDFIUM2)


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
) -> _MappedConversion:
    from docling.datamodel.base_models import ConversionStatus

    # Fast path: clean SUCCESS on the primary backend.
    if conversion is not None and getattr(conversion, "status", None) == ConversionStatus.SUCCESS:
        mapped = _mapped_from_success(conversion, config, backend=primary_backend)
        if mapped is not None:
            return mapped

    # Decide whether adaptive recovery applies.
    can_recover = False
    failed_pages: list[int] = []
    if conversion is not None:
        status = getattr(conversion, "status", None)
        failed_pages = _failed_page_numbers(conversion)
        if (
            status == ConversionStatus.PARTIAL_SUCCESS
            and failed_pages
            and _result_has_memory_errors(conversion)
        ):
            can_recover = True

    # Whole-document pypdfium2 fallback for hard raises or too many failed pages.
    need_whole_fallback = primary_raised
    if can_recover:
        total_pages = _page_count_estimate(conversion, failed_pages)
        ratio = len(failed_pages) / max(total_pages, 1)
        if ratio > _MAX_RECOVERABLE_PAGE_RATIO:
            need_whole_fallback = True

    if need_whole_fallback or (not can_recover and primary_raised):
        return _whole_document_pypdfium2_fallback(
            source_path=source_path,
            config=config,
            cancel=cancel,
            prior=conversion,
        )

    if not can_recover:
        # Document-scoped / non-memory partial failures keep today's reject path.
        if conversion is None:
            raise ValueError(
                "Docling conversion failed and recovery could not obtain a result."
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
        )

    pages, blocks = map_docling_document(document)
    # Drop chunks that touch failed pages; they will be replaced by recovery.
    failed_set = set(failed_pages)
    all_chunks = _chunk_document(document, blocks, config)
    chunks = [
        chunk
        for chunk in all_chunks
        if chunk.page_start not in failed_set and chunk.page_end not in failed_set
    ]
    # Also drop blocks/pages for failed pages so recovered content replaces them.
    pages = [page for page in pages if page.page_number not in failed_set]
    blocks = [block for block in blocks if block.page_number not in failed_set]

    unrecoverable: list[int] = []
    for page_no in failed_pages:
        _raise_if_cancelled(cancel)
        recovered = _convert_single_page(
            source_path,
            page_no,
            config,
            _converter._PDF_BACKEND_DOCLING_PARSE,
        )
        backend_used = _converter._PDF_BACKEND_DOCLING_PARSE
        if recovered is None:
            recovered = _convert_single_page(
                source_path,
                page_no,
                config,
                _converter._PDF_BACKEND_PYPDFIUM2,
            )
            backend_used = _converter._PDF_BACKEND_PYPDFIUM2
        if recovered is None:
            unrecoverable.append(page_no)
            continue
        pages, blocks, chunks = _merge_recovered_page(
            pages, blocks, chunks, page_no, recovered
        )
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
