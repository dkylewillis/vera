from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..types import ParsedBlock, ParsedPage

_CAPTION_RE = re.compile(
    r"^(figure|fig\.?|table|diagram|exhibit|chart|map|photo|illustration|plate|drawing)\s*[0-9]+([.:\-\u2013]|\s|$)",
    re.I,
)
_CAPTION_PROXIMITY = 60.0  # max vertical gap in points between caption and image
# Embedded images smaller than this in *both* dimensions (PDF points) are treated
# as decorative noise (icons, bullets, letterhead marks) rather than figures.
_MIN_FIGURE_DIMENSION = 20.0
# Drop PyMuPDF paragraph blocks when this fraction of the block area lies inside
# a pdfplumber-detected table region (avoids indexing garbled cell text twice).
_TABLE_OVERLAP_THRESHOLD = 0.5
_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
}
_OCR_MODES = {"auto", "off", "force"}
_OCR_MIN_USEFUL_CHARACTERS = 10
_OCR_IMAGE_COVERAGE_THRESHOLD = 0.5


def _open_fitz():
    try:
        import fitz  # PyMuPDF
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "PyMuPDF is required for PDF parsing: install vera-ingest"
        ) from exc
    return fitz


def _open_pdfplumber():
    try:
        import pdfplumber
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pdfplumber is required for PDF table parsing") from exc
    return pdfplumber


def parse_pdf(path: str) -> list[ParsedPage]:
    fitz = _open_fitz()
    doc = fitz.open(path)
    pages: list[ParsedPage] = []
    try:
        for idx, page in enumerate(doc, start=1):
            rect = page.rect
            text = page.get_text("text") or ""
            pages.append(ParsedPage(idx, float(rect.width), float(rect.height), text.strip()))
    finally:
        doc.close()
    return pages


@dataclass
class _RawBlock:
    page_number: int
    text: str
    bbox: tuple[float, float, float, float]
    dominant_size: float
    bold: bool
    line_count: int
    image_bytes: bytes | None = None
    image_ext: str = ""
    rotated: bool = False
    ocr: bool = False


def _bbox_coverage(
    bbox: tuple[float, float, float, float],
    *,
    page_width: float,
    page_height: float,
) -> float:
    page_area = max(0.0, page_width) * max(0.0, page_height)
    if page_area <= 0.0:
        return 0.0
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    return min(1.0, (width * height) / page_area)


def _page_needs_ocr(page_text: str, layout: dict[str, Any], *, width: float, height: float) -> bool:
    useful_characters = sum(character.isalnum() for character in page_text)
    has_large_image = any(
        block.get("type") == 1
        and _bbox_coverage(
            tuple(float(value) for value in block.get("bbox", (0, 0, 0, 0))),
            page_width=width,
            page_height=height,
        )
        >= _OCR_IMAGE_COVERAGE_THRESHOLD
        for block in layout.get("blocks", [])
    )
    if useful_characters < _OCR_MIN_USEFUL_CHARACTERS:
        # Do not send genuinely blank pages through OCR. A scanned page normally
        # appears as a large image covering most of the page.
        return has_large_image
    return False


def _bundled_tessdata(language: str) -> str | None:
    """Return bundled language data when it covers the full selection."""
    directory = Path(__file__).resolve().parents[1] / "tessdata"
    languages = [item.strip() for item in language.split("+") if item.strip()]
    if languages and all((directory / f"{item}.traineddata").is_file() for item in languages):
        return str(directory)
    return None


def _ocr_page_content(page, *, language: str, dpi: int) -> tuple[str, dict[str, Any]]:
    tessdata = _bundled_tessdata(language)
    try:
        textpage = page.get_textpage_ocr(
            language=language,
            dpi=dpi,
            full=True,
            tessdata=tessdata,
        )
        return (
            page.get_text("text", textpage=textpage) or "",
            page.get_text("dict", textpage=textpage),
        )
    except Exception as exc:
        if language == "eng" and tessdata is None:
            requirement = "bundled English OCR data was not found; reinstall VERA"
        elif tessdata is None:
            requirement = (
                f"language data for '{language}' is not bundled; install that tessdata "
                "and configure TESSDATA_PREFIX"
            )
        else:
            requirement = f"bundled language data for '{language}' could not be loaded"
        raise RuntimeError(
            f"OCR failed for page {page.number + 1}: {requirement}. Original error: {exc}"
        ) from exc


def _span_is_bold(span: dict) -> bool:
    return bool(span.get("flags", 0) & 16)


def _raise_if_cancelled(cancel: Any | None) -> None:
    if cancel is None:
        return
    interrupted = getattr(cancel, "raise_if_interrupted", None)
    if callable(interrupted):
        interrupted()
        return
    raise_if_cancelled = getattr(cancel, "raise_if_cancelled", None)
    if callable(raise_if_cancelled):
        raise_if_cancelled()


def _collect_raw_blocks(
    doc,
    *,
    ocr_mode: str = "auto",
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    cancel: Any | None = None,
) -> tuple[list[ParsedPage], list[_RawBlock], Counter, list[int]]:
    pages: list[ParsedPage] = []
    raw: list[_RawBlock] = []
    size_weights: Counter = Counter()
    ocr_pages: list[int] = []
    for idx, page in enumerate(doc, start=1):
        _raise_if_cancelled(cancel)
        page_raw: list[_RawBlock] = []
        try:
            rect = page.rect
            width = float(rect.width)
            height = float(rect.height)
            native_text = page.get_text("text") or ""
            native_layout = page.get_text("dict")
            use_ocr = ocr_mode == "force" or (
                ocr_mode == "auto"
                and _page_needs_ocr(native_text, native_layout, width=width, height=height)
            )
            if use_ocr:
                page_text, text_layout = _ocr_page_content(
                    page,
                    language=ocr_language,
                    dpi=ocr_dpi,
                )
                # Tesseract runs inside PyMuPDF and cannot be interrupted in the
                # middle of this call. Honor stop/skip as soon as it returns.
                _raise_if_cancelled(cancel)
                ocr_pages.append(idx)
            else:
                page_text = native_text
                text_layout = native_layout
        except Exception:
            # Closing the document from another thread (stop/skip) surfaces here.
            _raise_if_cancelled(cancel)
            raise
        pages.append(ParsedPage(idx, width, height, page_text.strip()))

        # Always source images from the native PDF layout. OCR TextPage output
        # contains recognized text and coordinates, but not the original image bytes.
        for block in native_layout.get("blocks", []):
            bbox = tuple(float(v) for v in block.get("bbox", (0, 0, 0, 0)))
            if block.get("type") == 1:
                page_raw.append(
                    _RawBlock(idx, "", bbox, 0.0, False, 0, block.get("image"), block.get("ext", "png"))
                )
        for block in text_layout.get("blocks", []):
            if block.get("type") == 1:
                continue
            bbox = tuple(float(v) for v in block.get("bbox", (0, 0, 0, 0)))
            lines = block.get("lines", [])
            block_sizes: Counter = Counter()
            texts: list[str] = []
            bold_chars = 0
            total_chars = 0
            rotated_lines = 0
            for line in lines:
                direction = line.get("dir", (1.0, 0.0))
                if abs(float(direction[0])) < 0.99:
                    rotated_lines += 1
                line_parts: list[str] = []
                prev_x1: float | None = None
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    stripped = text.strip()
                    if not stripped:
                        continue
                    span_bbox = span.get("bbox") or (0.0, 0.0, 0.0, 0.0)
                    span_x0 = float(span_bbox[0])
                    span_x1 = float(span_bbox[2])
                    span_size = float(span.get("size", 0.0)) or 0.0
                    # PyMuPDF often emits each word of justified text as its own
                    # span with no trailing space, which would glue words together
                    # ("elementsshallbeinstalled"). Insert a space when the visual
                    # gap to the previous span looks like a word boundary.
                    if line_parts and prev_x1 is not None:
                        gap = span_x0 - prev_x1
                        prev_ends_space = line_parts[-1][-1:].isspace()
                        starts_space = text[:1].isspace()
                        if not prev_ends_space and not starts_space and gap > max(1.0, 0.2 * span_size):
                            line_parts.append(" ")
                    line_parts.append(text)
                    prev_x1 = span_x1
                    size = round(span_size, 1)
                    block_sizes[size] += len(stripped)
                    size_weights[size] += len(stripped)
                    total_chars += len(stripped)
                    if _span_is_bold(span):
                        bold_chars += len(stripped)
                if line_parts:
                    texts.append("".join(line_parts).strip())
            text = "\n".join(t for t in texts if t).strip()
            if not text:
                continue
            dominant = block_sizes.most_common(1)[0][0] if block_sizes else 0.0
            bold = total_chars > 0 and bold_chars / total_chars > 0.8
            rotated = len(lines) > 0 and rotated_lines == len(lines)
            page_raw.append(
                _RawBlock(
                    idx,
                    text,
                    bbox,
                    dominant,
                    bold,
                    len(texts),
                    rotated=rotated,
                    ocr=use_ocr,
                )
            )
        page_raw.sort(key=lambda block: (block.bbox[1], block.bbox[0]))
        raw.extend(page_raw)
    return pages, raw, size_weights, ocr_pages


def parse_pdf_structured(
    path: str,
    *,
    ocr_mode: str = "auto",
    ocr_language: str = "eng",
    ocr_dpi: int = 300,
    diagnostics: dict[str, Any] | None = None,
    cancel: Any | None = None,
) -> tuple[list[ParsedPage], list[ParsedBlock]]:
    """Parse a PDF into pages plus structured blocks.

    Detects headings via font size/weight relative to body text, keeps
    paragraphs as text blocks, and captures embedded images as image blocks.
    """
    if ocr_mode not in _OCR_MODES:
        raise ValueError(f"ocr_mode must be one of {sorted(_OCR_MODES)}")
    if not ocr_language.strip():
        raise ValueError("ocr_language must not be empty")
    if ocr_dpi <= 0:
        raise ValueError("ocr_dpi must be positive")

    fitz = _open_fitz()
    doc = fitz.open(path)
    register = getattr(cancel, "register_response", None) if cancel is not None else None
    unregister = getattr(cancel, "unregister_response", None) if cancel is not None else None
    try:
        if callable(register):
            register(doc)
        pages, raw, size_weights, ocr_pages = _collect_raw_blocks(
            doc,
            ocr_mode=ocr_mode,
            ocr_language=ocr_language,
            ocr_dpi=ocr_dpi,
            cancel=cancel,
        )
    except Exception:
        _raise_if_cancelled(cancel)
        raise
    finally:
        if callable(unregister):
            try:
                unregister(doc)
            except Exception:
                pass
        try:
            doc.close()
        except Exception:
            pass
    if diagnostics is not None:
        diagnostics.update(
            {
                "ocr_engine": "tesseract",
                "ocr_mode": ocr_mode,
                "ocr_language": ocr_language,
                "ocr_dpi": ocr_dpi,
                "ocr_pages": ocr_pages,
            }
        )

    body_size = size_weights.most_common(1)[0][0] if size_weights else 11.0

    def is_heading(block: _RawBlock) -> bool:
        if block.rotated or block.ocr:
            return False
        if not block.text or len(block.text) > 300 or block.line_count > 3:
            return False
        if block.dominant_size >= body_size + 0.9:
            return True
        return block.bold and block.dominant_size >= body_size and len(block.text) < 120

    heading_sizes = sorted(
        {b.dominant_size for b in raw if b.text and is_heading(b)}, reverse=True
    )
    size_to_level = {size: min(idx + 1, 6) for idx, size in enumerate(heading_sizes)}

    blocks: list[ParsedBlock] = []
    for block in raw:
        if block.image_bytes is not None:
            width = block.bbox[2] - block.bbox[0]
            height = block.bbox[3] - block.bbox[1]
            if width < _MIN_FIGURE_DIMENSION and height < _MIN_FIGURE_DIMENSION:
                # Too small to be a real figure — an icon, bullet, or decorative
                # mark rather than something worth surfacing as a "figure".
                continue
            blocks.append(
                ParsedBlock(
                    page_number=block.page_number,
                    block_type="image",
                    text="",
                    bbox=block.bbox,
                    image_bytes=block.image_bytes,
                    image_ext=block.image_ext or "png",
                )
            )
        elif is_heading(block):
            blocks.append(
                ParsedBlock(
                    page_number=block.page_number,
                    block_type="heading",
                    text=" ".join(block.text.split()),
                    bbox=block.bbox,
                    heading_level=size_to_level.get(block.dominant_size, 6),
                )
            )
        else:
            blocks.append(
                ParsedBlock(
                    page_number=block.page_number,
                    block_type="paragraph",
                    text=block.text,
                    bbox=block.bbox,
                )
            )
    tables = _extract_tables_from_pdf(path)
    blocks = _merge_tables_into_blocks(blocks, tables)
    _mark_captions(blocks)
    return pages, blocks


def _clean_table_cell(cell: str | None) -> str:
    if cell is None:
        return ""
    return str(cell).replace("|", "\\|").replace("\n", " ").strip()


def _table_to_markdown(table: list[list[str | None]]) -> str:
    """Convert a pdfplumber table grid to GitHub-flavored markdown."""
    if not table or not table[0]:
        return ""

    header = [_clean_table_cell(cell) for cell in table[0]]
    if not any(header):
        return ""

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * len(header)) + " |",
    ]
    for row in table[1:]:
        cells = [_clean_table_cell(cell) for cell in row]
        while len(cells) < len(header):
            cells.append("")
        lines.append("| " + " | ".join(cells[: len(header)]) + " |")
    return "\n".join(lines)


def _extract_tables_from_pdf(path: str) -> list[dict[str, object]]:
    """Extract bordered tables with pdfplumber."""
    pdfplumber = _open_pdfplumber()
    tables: list[dict[str, object]] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            for table_idx, table in enumerate(page.find_tables(_TABLE_SETTINGS)):
                data = table.extract()
                if not data or len(data) < 2:
                    continue
                markdown = _table_to_markdown(data)
                if not markdown:
                    continue
                bbox = tuple(float(v) for v in table.bbox)
                tables.append(
                    {
                        "table_text": markdown,
                        "page_number": page_num,
                        "table_index": table_idx,
                        "bbox": bbox,
                    }
                )
    return tables


def _bbox_area(bbox: tuple[float, float, float, float]) -> float:
    width = max(0.0, bbox[2] - bbox[0])
    height = max(0.0, bbox[3] - bbox[1])
    return width * height


def _intersection_area(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    x0 = max(a[0], b[0])
    y0 = max(a[1], b[1])
    x1 = min(a[2], b[2])
    y1 = min(a[3], b[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def _overlap_fraction(
    block_bbox: tuple[float, float, float, float],
    table_bbox: tuple[float, float, float, float],
) -> float:
    block_area = _bbox_area(block_bbox)
    if block_area <= 0.0:
        return 0.0
    return _intersection_area(block_bbox, table_bbox) / block_area


def _merge_tables_into_blocks(
    blocks: list[ParsedBlock],
    tables: list[dict[str, object]],
    *,
    overlap_threshold: float = _TABLE_OVERLAP_THRESHOLD,
) -> list[ParsedBlock]:
    """Insert table blocks and drop paragraph text duplicated inside table regions."""
    if not tables:
        return blocks

    table_bboxes_by_page: dict[int, list[tuple[float, float, float, float]]] = {}
    for table in tables:
        page_number = int(table["page_number"])
        bbox = table["bbox"]
        assert isinstance(bbox, tuple)
        table_bboxes_by_page.setdefault(page_number, []).append(bbox)

    kept: list[ParsedBlock] = []
    for block in blocks:
        if block.block_type != "paragraph" or block.bbox is None:
            kept.append(block)
            continue
        overlaps = table_bboxes_by_page.get(block.page_number, [])
        if any(_overlap_fraction(block.bbox, table_bbox) >= overlap_threshold for table_bbox in overlaps):
            continue
        kept.append(block)

    table_blocks = [
        ParsedBlock(
            page_number=int(table["page_number"]),
            block_type="table",
            text=str(table["table_text"]),
            bbox=table["bbox"],  # type: ignore[arg-type]
        )
        for table in tables
    ]

    merged = kept + table_blocks
    merged.sort(key=lambda block: (block.page_number, block.bbox[1] if block.bbox else float("inf")))
    return merged


def _vertical_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Vertical distance between two bboxes (0 when they overlap vertically)."""
    if a[3] < b[1]:
        return b[1] - a[3]
    if b[3] < a[1]:
        return a[1] - b[3]
    return 0.0


def _mark_captions(blocks: list[ParsedBlock]) -> None:
    """Reclassify text blocks as captions when they label a nearby image.

    A caption starts with a figure/table label (e.g. "Figure 3:") and sits
    vertically adjacent to an image block on the same page.
    """
    images_by_page: dict[int, list[ParsedBlock]] = {}
    for block in blocks:
        if block.block_type == "image":
            images_by_page.setdefault(block.page_number, []).append(block)
    for block in blocks:
        if block.block_type not in {"paragraph", "heading"}:
            continue
        first_line = block.text.splitlines()[0].strip() if block.text else ""
        if not _CAPTION_RE.match(first_line) or len(block.text) > 500:
            continue
        images = images_by_page.get(block.page_number, [])
        if not images or block.bbox is None:
            continue
        if any(
            img.bbox is not None and _vertical_gap(block.bbox, img.bbox) <= _CAPTION_PROXIMITY
            for img in images
        ):
            block.block_type = "caption"
            block.heading_level = None
