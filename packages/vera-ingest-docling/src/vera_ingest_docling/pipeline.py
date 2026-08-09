"""Docling DocumentConverter + HybridChunker ingest pipeline."""

from __future__ import annotations

import io
from collections import defaultdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from vera_ingest.pipeline import UnknownIngestPipelineError
from vera_ingest.types import IngestBlock, IngestChunk, IngestOptions, IngestResult, ParsedPage


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


# RapidOCR onnxruntime language codes observed from the installed engine.
# Keep in sync with RapidOCR's supported recognition languages.
_RAPIDOCR_LANGS = frozenset(
    {
        "af",
        "arabic",
        "az",
        "bs",
        "ca",
        "ch",
        "chinese_cht",
        "cs",
        "cy",
        "cyrillic",
        "da",
        "de",
        "devanagari",
        "el",
        "en",
        "es",
        "eslav",
        "et",
        "eu",
        "fi",
        "fr",
        "french",
        "ga",
        "german",
        "gl",
        "hr",
        "hu",
        "id",
        "is",
        "it",
        "japan",
        "korean",
        "ku",
        "la",
        "latin",
        "lb",
        "lt",
        "lv",
        "mi",
        "ms",
        "mt",
        "nl",
        "no",
        "oc",
        "pl",
        "pt",
        "qu",
        "rm",
        "ro",
        "rs_latin",
        "sk",
        "sl",
        "sq",
        "sv",
        "sw",
        "ta",
        "te",
        "th",
        "tl",
        "tr",
        "uz",
        "vi",
    }
)

# Common Tesseract / ISO-639-3 codes (VERA CLI default is ``eng``) → RapidOCR.
_TESSERACT_TO_RAPIDOCR = {
    "afr": "af",
    "ara": "arabic",
    "aze": "az",
    "bos": "bs",
    "bul": "cyrillic",
    "cat": "ca",
    "ces": "cs",
    "chi_sim": "ch",
    "chi_tra": "chinese_cht",
    "cym": "cy",
    "cze": "cs",
    "dan": "da",
    "deu": "de",
    "dut": "nl",
    "ell": "el",
    "eng": "en",
    "est": "et",
    "eus": "eu",
    "baq": "eu",
    "fin": "fi",
    "fra": "fr",
    "fre": "fr",
    "ger": "de",
    "gle": "ga",
    "glg": "gl",
    "gre": "el",
    "hin": "devanagari",
    "hrv": "hr",
    "hun": "hu",
    "ice": "is",
    "ind": "id",
    "isl": "is",
    "ita": "it",
    "jpn": "japan",
    "kor": "korean",
    "kur": "ku",
    "lat": "la",
    "lav": "lv",
    "lit": "lt",
    "ltz": "lb",
    "may": "ms",
    "mlt": "mt",
    "mri": "mi",
    "msa": "ms",
    "nld": "nl",
    "nor": "no",
    "oci": "oc",
    "pol": "pl",
    "por": "pt",
    "que": "qu",
    "roh": "rm",
    "ron": "ro",
    "rum": "ro",
    "rus": "cyrillic",
    "san": "devanagari",
    "slk": "sk",
    "slo": "sk",
    "slv": "sl",
    "spa": "es",
    "sqi": "sq",
    "alb": "sq",
    "swa": "sw",
    "swe": "sv",
    "tam": "ta",
    "tel": "te",
    "tgl": "tl",
    "fil": "tl",
    "tha": "th",
    "tur": "tr",
    "ukr": "cyrillic",
    "uzb": "uz",
    "vie": "vi",
}


def map_rapidocr_languages(ocr_language: str | None) -> list[str]:
    """Map VERA/Tesseract OCR language codes to RapidOCR language codes.

    VERA's default ``eng`` is Tesseract-style; RapidOCR expects ``en``. Accepts
    ``+`` or ``,`` separated lists and passes through codes that are already
    RapidOCR-native.
    """
    raw = (ocr_language or "eng").strip()
    if not raw:
        raw = "eng"
    parts = [part.strip().lower() for part in raw.replace("+", ",").split(",") if part.strip()]
    if not parts:
        parts = ["eng"]

    mapped: list[str] = []
    unknown: list[str] = []
    for part in parts:
        rapid = _TESSERACT_TO_RAPIDOCR.get(part, part)
        # Prefer canonical short codes when RapidOCR aliases exist.
        if rapid == "french":
            rapid = "fr"
        elif rapid == "german":
            rapid = "de"
        if rapid not in _RAPIDOCR_LANGS:
            unknown.append(part)
            continue
        if rapid not in mapped:
            mapped.append(rapid)

    if unknown:
        supported = ", ".join(sorted(_RAPIDOCR_LANGS))
        raise ValueError(
            "Docling/RapidOCR does not support OCR language "
            f"{', '.join(unknown)!r} (from {ocr_language!r}). "
            "Use a RapidOCR code such as 'en', or a mapped Tesseract alias "
            f"such as 'eng'. Supported RapidOCR codes: {supported}."
        )
    return mapped


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


def _build_converter(options: IngestOptions) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    ocr_mode = (options.ocr_mode or "auto").strip().lower()
    if ocr_mode not in {"auto", "off", "force"}:
        raise ValueError(f"Unsupported OCR mode {options.ocr_mode!r}; use auto, off, or force.")

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
        )
        rapid_langs = map_rapidocr_languages(options.ocr_language)
        if hasattr(ocr_options, "lang"):
            ocr_options.lang = rapid_langs
        pipeline_options.ocr_options = ocr_options

    return DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        },
    )


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
    if "bad_alloc" in blob:
        hints.append(
            "Docling ran out of memory rasterizing pages; large manuals need the "
            "default images_scale (not OCR-DPI scaling)."
        )
    if hints:
        return f"{joined} Hint: {' '.join(hints)}"
    return joined


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
        f"Partial or failed results are rejected in this release.{suffix}"
    )


def _chunk_document(
    document: Any,
    blocks: list[IngestBlock],
    options: IngestOptions,
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
                    "overlap_requested": int(options.overlap),
                },
            )
        )
    return chunks


class DoclingHybridPipeline:
    """Optional Docling parsing pipeline with HybridChunker output."""

    def ingest(self, source_path: str, options: IngestOptions) -> IngestResult:
        variant = (options.variant or "hybrid").strip().lower()
        if variant not in {"", "hybrid"}:
            raise UnknownIngestPipelineError(
                f"Unknown Docling pipeline variant {options.variant!r}; use 'docling' or 'docling:hybrid'."
            )
        _raise_if_cancelled(options.cancel)
        converter = _build_converter(options)
        _raise_if_cancelled(options.cancel)
        conversion = converter.convert(source=source_path)
        _raise_if_cancelled(options.cancel)
        document = _assert_conversion_ok(conversion)
        pages, blocks = map_docling_document(document)
        _raise_if_cancelled(options.cancel)
        chunks = _chunk_document(document, blocks, options)
        _raise_if_cancelled(options.cancel)
        return IngestResult(
            pages=pages,
            blocks=blocks,
            chunks=chunks,
            parser_name="docling",
            parser_version=_docling_version(),
            chunking_strategy=(
                f"docling_hybrid:{int(options.chunk_size)}"
                f"(overlap_ignored:{int(options.overlap)})"
            ),
            diagnostics={
                "engine": "docling",
                "variant": "hybrid",
                "ocr_mode": options.ocr_mode,
                "ocr_language": options.ocr_language,
                "ocr_language_rapidocr": (
                    map_rapidocr_languages(options.ocr_language)
                    if (options.ocr_mode or "auto").strip().lower() != "off"
                    else []
                ),
                "ocr_dpi": options.ocr_dpi,
                "images_scale": 1.0,
                "torch_compile": False,
                "overlap_ignored": True,
                "overlap_requested": int(options.overlap),
                "artifacts_path_env": "DOCLING_ARTIFACTS_PATH",
            },
        )
