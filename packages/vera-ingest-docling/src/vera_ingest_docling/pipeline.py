"""Docling DocumentConverter + HybridChunker ingest pipeline."""

from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from vera_ingest.pipeline import UnknownIngestPipelineError
from vera_ingest.types import IngestBlock, IngestChunk, IngestRequest, IngestResult, ParsedPage, coerce_ingest_request

from .options import DoclingOptions

# Above this ratio of failed pages, skip per-page recovery and reconvert the
# whole document once with pypdfium2 (avoids paying model-init per page).
_MAX_RECOVERABLE_PAGE_RATIO = 0.2
_PDF_BACKEND_DOCLING_PARSE = "docling_parse"
_PDF_BACKEND_PYPDFIUM2 = "pypdfium2"


def _split_ocr_languages(ocr_language: str) -> list[str]:
    """Split a ``+``/``,``-joined RapidOCR-native language string into codes.

    No translation or validation against a known set happens here — VERA no
    longer maintains a Tesseract-to-RapidOCR alias table; an unrecognized
    code is rejected by RapidOCR itself when OCR actually runs.
    """
    parts = [part.strip().lower() for part in (ocr_language or "en").replace("+", ",").split(",")]
    codes = [part for part in parts if part]
    return codes or ["en"]


def _docling_version() -> str:
    try:
        return version("docling")
    except PackageNotFoundError:  # pragma: no cover
        return "unknown"


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


def _block_id_from_ref(self_ref: str) -> str:
    ref = (self_ref or "").strip()
    if ref.startswith("#/"):
        ref = ref[2:]
    elif ref.startswith("#"):
        ref = ref[1:]
    ref = ref.strip("/").replace("/", "_")
    return ref or "block"


class WhitespaceTokenizer(BaseTokenizer):
    """Deterministic whitespace tokenizer for HybridChunker token limits.

    Avoids implicit HuggingFace tokenizer downloads. ``get_tokenizer()`` returns
    ``count_tokens`` so ``semchunk`` can use the same counting function.
    """

    max_tokens: int = 500

    def count_tokens(self, text: str) -> int:
        stripped = (text or "").strip()
        if not stripped:
            return 0
        return len(stripped.split())

    def get_max_tokens(self) -> int:
        return int(self.max_tokens)

    def get_tokenizer(self) -> Any:
        return self.count_tokens


def _page_height(document: Any, page_no: int) -> float | None:
    pages = getattr(document, "pages", None) or {}
    page = pages.get(page_no)
    if page is None:
        return None
    size = getattr(page, "size", None)
    if size is None:
        return None
    height = getattr(size, "height", None)
    return float(height) if height is not None else None


def _page_width(document: Any, page_no: int) -> float | None:
    pages = getattr(document, "pages", None) or {}
    page = pages.get(page_no)
    if page is None:
        return None
    size = getattr(page, "size", None)
    if size is None:
        return None
    width = getattr(size, "width", None)
    return float(width) if width is not None else None


def _bbox_to_top_left(
    bbox: Any,
    page_height: float | None,
) -> tuple[float, float, float, float] | None:
    if bbox is None:
        return None
    origin = getattr(bbox, "coord_origin", None)
    origin_value = getattr(origin, "value", origin)
    if str(origin_value).upper() == "BOTTOMLEFT":
        if page_height is None:
            return None
        converted = bbox.to_top_left_origin(page_height)
        return (float(converted.l), float(converted.t), float(converted.r), float(converted.b))
    return (float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b))


def _item_regions(document: Any, item: Any) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for prov in getattr(item, "prov", None) or []:
        page_no = int(getattr(prov, "page_no", 0) or 0)
        if page_no <= 0:
            continue
        height = _page_height(document, page_no)
        width = _page_width(document, page_no)
        bbox = _bbox_to_top_left(getattr(prov, "bbox", None), height)
        if bbox is None:
            continue
        regions.append(
            {
                "page_number": page_no,
                "bbox": bbox,
                "page_width": width,
                "page_height": height,
            }
        )
    return regions


def _primary_page_and_bbox(
    regions: list[dict[str, Any]],
) -> tuple[int, tuple[float, float, float, float] | None]:
    if not regions:
        return 1, None
    first = regions[0]
    bbox = first.get("bbox")
    page = int(first["page_number"])
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        return page, (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
    return page, None


def _label_name(item: Any) -> str:
    label = getattr(item, "label", None)
    if label is None:
        return type(item).__name__.lower()
    return str(getattr(label, "value", label)).lower()


def _classify_item(item: Any) -> str | None:
    from docling_core.types.doc import (
        PictureItem,
        SectionHeaderItem,
        TableItem,
        TitleItem,
    )

    if isinstance(item, (TitleItem, SectionHeaderItem)):
        return "heading"
    if isinstance(item, TableItem):
        return "table"
    if isinstance(item, PictureItem):
        return "image"
    label = _label_name(item)
    if label in {"caption"}:
        return "caption"
    if label in {
        "paragraph",
        "text",
        "list_item",
        "code",
        "formula",
        "footnote",
        "reference",
        "checkbox_selected",
        "checkbox_unselected",
        "page_header",
        "page_footer",
    }:
        return "paragraph"
    # Skip structural groups and furniture-only labels without searchable text.
    if label in {"title", "section_header"}:
        return "heading"
    return None


def _item_text(document: Any, item: Any, block_type: str) -> str:
    from docling_core.types.doc import PictureItem, TableItem

    if isinstance(item, TableItem):
        try:
            return item.export_to_markdown(doc=document)
        except TypeError:
            return item.export_to_markdown()
        except Exception:  # noqa: BLE001 - fall back to raw text fields
            return str(getattr(item, "text", "") or "")
    if isinstance(item, PictureItem):
        return str(getattr(item, "text", "") or getattr(item, "captions", "") or "")
    if block_type == "caption":
        return str(getattr(item, "text", "") or "")
    return str(getattr(item, "text", "") or getattr(item, "orig", "") or "")


def _picture_bytes(document: Any, item: Any) -> tuple[bytes | None, str]:
    get_image = getattr(item, "get_image", None)
    image = None
    if callable(get_image):
        try:
            image = get_image(doc=document)
        except TypeError:
            image = get_image(document)
        except Exception:  # noqa: BLE001
            image = None
    if image is None:
        ref = getattr(item, "image", None)
        pil = getattr(ref, "pil_image", None) if ref is not None else None
        image = pil
    if image is None:
        return None, ""
    buffer = io.BytesIO()
    try:
        image.save(buffer, format="PNG")
    except Exception:  # noqa: BLE001
        return None, ""
    return buffer.getvalue(), "png"


def _heading_level(item: Any) -> int | None:
    from docling_core.types.doc import SectionHeaderItem, TitleItem

    if isinstance(item, TitleItem):
        return 1
    if isinstance(item, SectionHeaderItem):
        level = getattr(item, "level", 1)
        try:
            return max(1, int(level))
        except (TypeError, ValueError):
            return 1
    return None


def map_docling_document(document: Any) -> tuple[list[ParsedPage], list[IngestBlock]]:
    """Normalize a DoclingDocument into VERA ingest pages and blocks."""
    blocks: list[IngestBlock] = []
    page_texts: dict[int, list[str]] = defaultdict(list)
    seen_ids: set[str] = set()

    iterate = getattr(document, "iterate_items", None)
    items: list[Any]
    if callable(iterate):
        items = [item for item, _level in iterate()]
    else:
        items = list(getattr(document, "texts", []) or [])
        items.extend(getattr(document, "tables", []) or [])
        items.extend(getattr(document, "pictures", []) or [])

    for item in items:
        block_type = _classify_item(item)
        if block_type is None:
            continue
        self_ref = str(getattr(item, "self_ref", "") or "")
        block_id = _block_id_from_ref(self_ref)
        if block_id in seen_ids:
            suffix = 2
            while f"{block_id}_{suffix}" in seen_ids:
                suffix += 1
            block_id = f"{block_id}_{suffix}"
        seen_ids.add(block_id)

        regions = _item_regions(document, item)
        page_number, bbox = _primary_page_and_bbox(regions)
        text = _item_text(document, item, block_type).strip()
        image_bytes: bytes | None = None
        image_ext = ""
        if block_type == "image":
            image_bytes, image_ext = _picture_bytes(document, item)
        if not text and not image_bytes:
            continue
        if text:
            page_texts[page_number].append(text)
        blocks.append(
            IngestBlock(
                block_id=block_id,
                page_number=page_number,
                block_type=block_type,
                text=text,
                bbox=bbox,
                heading_level=_heading_level(item),
                image_bytes=image_bytes,
                image_ext=image_ext,
                regions=regions,
            )
        )

    pages: list[ParsedPage] = []
    page_numbers = sorted(
        set(getattr(document, "pages", {}).keys()) | set(page_texts.keys())
    )
    if not page_numbers:
        page_numbers = [1]
    for page_no in page_numbers:
        page_no_int = int(page_no)
        pages.append(
            ParsedPage(
                page_number=page_no_int,
                width=_page_width(document, page_no_int),
                height=_page_height(document, page_no_int),
                text="\n".join(page_texts.get(page_no_int, [])),
            )
        )
    return pages, blocks


def _disable_torch_compile() -> None:
    """Avoid torch.compile / Inductor, which requires MSVC ``cl.exe`` on Windows.

    Docling enables ``compile_torch_models`` by default. On machines without Visual
    Studio Build Tools that fails page-by-page with \"Compiler: cl is not found\"
    and often cascades into memory exhaustion.
    """
    try:
        from docling.datamodel.settings import settings

        settings.inference.compile_torch_models = False
    except Exception:  # pragma: no cover - defensive against Docling API drift
        pass
    try:
        import torch._dynamo

        torch._dynamo.config.suppress_errors = True
    except Exception:  # pragma: no cover - torch optional at import time
        pass


def _build_converter(options: DoclingOptions, *, backend: str | None = None) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ocr_mode = options.ocr_mode
    # Must run before PdfPipelineOptions() so default_factory compile flags are False.
    _disable_torch_compile()

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_table_structure = True
    pipeline_options.generate_picture_images = True
    # Keep Docling's default raster scale. Mapping VERA's Tesseract OCR DPI
    # (default 300) to images_scale (~4.17x) OOMs large manuals.
    pipeline_options.images_scale = 1.0
    layout_engine = getattr(getattr(pipeline_options, "layout_options", None), "engine_options", None)
    if layout_engine is not None and hasattr(layout_engine, "compile_model"):
        layout_engine.compile_model = False

    if ocr_mode == "off":
        pipeline_options.do_ocr = False
    else:
        pipeline_options.do_ocr = True
        ocr_options = RapidOcrOptions(
            force_full_page_ocr=(ocr_mode == "force"),
            lang=_split_ocr_languages(options.ocr_language),
        )
        pipeline_options.ocr_options = ocr_options

    selected = (backend or options.pdf_backend or _PDF_BACKEND_DOCLING_PARSE).strip().lower()
    format_kwargs: dict[str, Any] = {"pipeline_options": pipeline_options}
    if selected == _PDF_BACKEND_PYPDFIUM2:
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend

        format_kwargs["backend"] = PyPdfiumDocumentBackend

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(**format_kwargs),
        },
    )


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


def _chunk_document(
    document: Any,
    blocks: list[IngestBlock],
    options: DoclingOptions,
) -> list[IngestChunk]:
    from docling.chunking import HybridChunker

    block_by_ref = {block.block_id: block for block in blocks}
    tokenizer = WhitespaceTokenizer(max_tokens=max(1, int(options.chunk_size)))
    chunker = HybridChunker(tokenizer=tokenizer, merge_peers=True)
    chunks: list[IngestChunk] = []
    for index, chunk in enumerate(chunker.chunk(dl_doc=document), start=1):
        meta = getattr(chunk, "meta", None)
        doc_items = list(getattr(meta, "doc_items", None) or [])
        block_ids: list[str] = []
        page_numbers: list[int] = []
        for item in doc_items:
            block_id = _block_id_from_ref(str(getattr(item, "self_ref", "") or ""))
            if block_id in block_by_ref and block_id not in block_ids:
                block_ids.append(block_id)
            for prov in getattr(item, "prov", None) or []:
                page_no = int(getattr(prov, "page_no", 0) or 0)
                if page_no > 0:
                    page_numbers.append(page_no)
            mapped = block_by_ref.get(block_id)
            if mapped is not None:
                page_numbers.append(mapped.page_number)
        if not page_numbers and block_ids:
            page_numbers = [block_by_ref[block_id].page_number for block_id in block_ids]
        page_start = min(page_numbers) if page_numbers else 1
        page_end = max(page_numbers) if page_numbers else page_start
        headings = list(getattr(meta, "headings", None) or [])
        heading_path = " > ".join(str(part) for part in headings if str(part).strip())
        raw_text = str(getattr(chunk, "text", "") or "").strip()
        contextualized = str(chunker.contextualize(chunk=chunk) or "").strip()
        embedding_text = contextualized or None
        if not raw_text and embedding_text:
            raw_text = embedding_text
        if not raw_text:
            continue
        token_count = tokenizer.count_tokens(embedding_text or raw_text)
        chunks.append(
            IngestChunk(
                chunk_id=f"chunk_{index:06d}",
                text=raw_text,
                embedding_text=embedding_text,
                page_start=page_start,
                page_end=page_end,
                heading_path=heading_path,
                token_count=token_count,
                block_ids=block_ids,
                metadata={
                    "chunker": "docling_hybrid",
                    "overlap_ignored": True,
                },
            )
        )
    return chunks


@dataclass
class _MappedConversion:
    """Mapped/chunked output from a successful Docling conversion."""

    pages: list[ParsedPage]
    blocks: list[IngestBlock]
    chunks: list[IngestChunk]
    backend: str
    whole_fallback: str | None = None


def _try_convert(
    source_path: str,
    config: DoclingOptions,
    *,
    backend: str,
    page_range: tuple[int, int] | None = None,
) -> Any | None:
    """Run one Docling convert; return the ConversionResult or None on hard failure."""
    converter = _build_converter(config, backend=backend)
    try:
        if page_range is None:
            return converter.convert(source=source_path)
        return converter.convert(source=source_path, page_range=page_range)
    except Exception:  # noqa: BLE001 - catch native/process crashes from Docling
        return None


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
    result = _try_convert(
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


def _build_diagnostics(
    config: DoclingOptions,
    *,
    effective_backend: str,
    recovered_pages: list[int],
    recovered_pages_backend: dict[int, str],
    whole_document_fallback_backend: str | None,
) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {
        "engine": "docling",
        "variant": "hybrid",
        "ocr_mode": config.ocr_mode,
        "ocr_language": config.ocr_language,
        "ocr_languages": (
            _split_ocr_languages(config.ocr_language) if config.ocr_mode != "off" else []
        ),
        "images_scale": 1.0,
        "torch_compile": False,
        "overlap_ignored": True,
        "artifacts_path_env": "DOCLING_ARTIFACTS_PATH",
        "pdf_backend": effective_backend,
        "recovered_pages": list(recovered_pages),
    }
    if recovered_pages_backend:
        # JSON-friendly string keys for inspect/sidecar consumers.
        diagnostics["recovered_pages_backend"] = {
            str(page): backend for page, backend in sorted(recovered_pages_backend.items())
        }
    if whole_document_fallback_backend:
        diagnostics["whole_document_fallback_backend"] = whole_document_fallback_backend
    return diagnostics


class DoclingHybridPipeline:
    """Optional Docling parsing pipeline with HybridChunker output.

    Implements ``__call__`` (rather than a named ``ingest`` method) so an
    instance satisfies :data:`vera_ingest.pipeline.IngestPipeline` directly —
    a class is only needed here because Docling's recovery/fallback logic is
    decomposed into private helper methods, not because the pipeline holds
    state across calls.
    """

    def __call__(self, source_path: str, options: IngestRequest) -> IngestResult:
        request = coerce_ingest_request(options)
        variant = (request.variant or "hybrid").strip().lower()
        if variant not in {"", "hybrid"}:
            raise UnknownIngestPipelineError(
                f"Unknown Docling pipeline variant {request.variant!r}; use 'docling' or 'docling:hybrid'."
            )
        config = DoclingOptions.from_mapping(request.pipeline_options)
        _raise_if_cancelled(request.cancel)

        recovered_pages: list[int] = []
        recovered_pages_backend: dict[int, str] = {}
        whole_document_fallback_backend: str | None = None
        effective_backend = config.pdf_backend

        # Users who force pypdfium2 skip adaptive recovery on the primary pass.
        primary_backend = config.pdf_backend
        conversion: Any | None = None
        primary_raised = False
        try:
            converter = _build_converter(config, backend=primary_backend)
            _raise_if_cancelled(request.cancel)
            conversion = converter.convert(source=source_path)
        except Exception:  # noqa: BLE001 - Docling may raise on hard native crashes
            primary_raised = True
            conversion = None

        _raise_if_cancelled(request.cancel)
        mapped = self._resolve_conversion(
            source_path=source_path,
            config=config,
            conversion=conversion,
            primary_backend=primary_backend,
            primary_raised=primary_raised,
            cancel=request.cancel,
            recovered_pages=recovered_pages,
            recovered_pages_backend=recovered_pages_backend,
        )
        if mapped.whole_fallback:
            whole_document_fallback_backend = mapped.whole_fallback
            effective_backend = mapped.whole_fallback

        return IngestResult(
            pages=mapped.pages,
            blocks=mapped.blocks,
            chunks=mapped.chunks,
            parser_name="docling",
            parser_version=_docling_version(),
            chunking_strategy=f"docling_hybrid:{int(config.chunk_size)}",
            diagnostics=_build_diagnostics(
                config,
                effective_backend=effective_backend,
                recovered_pages=recovered_pages,
                recovered_pages_backend=recovered_pages_backend,
                whole_document_fallback_backend=whole_document_fallback_backend,
            ),
        )

    def _resolve_conversion(
        self,
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
            return self._whole_document_pypdfium2_fallback(
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
            return self._whole_document_pypdfium2_fallback(
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
                _PDF_BACKEND_DOCLING_PARSE,
            )
            backend_used = _PDF_BACKEND_DOCLING_PARSE
            if recovered is None:
                recovered = _convert_single_page(
                    source_path,
                    page_no,
                    config,
                    _PDF_BACKEND_PYPDFIUM2,
                )
                backend_used = _PDF_BACKEND_PYPDFIUM2
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

    def _whole_document_pypdfium2_fallback(
        self,
        *,
        source_path: str,
        config: DoclingOptions,
        cancel: Any | None,
        prior: Any | None,
    ) -> _MappedConversion:
        _raise_if_cancelled(cancel)
        if config.pdf_backend == _PDF_BACKEND_PYPDFIUM2:
            # Already on pypdfium2; nothing left to try.
            if prior is not None:
                _assert_conversion_ok(prior)
            raise ValueError(
                "Docling conversion failed with pdf_backend=pypdfium2; "
                "no further backend fallback is available."
            )
        result = _try_convert(
            source_path,
            config,
            backend=_PDF_BACKEND_PYPDFIUM2,
        )
        if result is None:
            if prior is not None:
                _assert_conversion_ok(prior)
            raise ValueError(
                "Docling conversion failed and the pypdfium2 whole-document "
                "fallback also failed."
            )
        mapped = _mapped_from_success(result, config, backend=_PDF_BACKEND_PYPDFIUM2)
        if mapped is None:
            _assert_conversion_ok(result)
            raise AssertionError("unreachable")  # pragma: no cover
        return replace(mapped, whole_fallback=_PDF_BACKEND_PYPDFIUM2)
