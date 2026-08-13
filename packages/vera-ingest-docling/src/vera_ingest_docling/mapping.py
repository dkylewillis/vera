"""Map a Docling document into VERA ingest pages, blocks, and chunks."""

from __future__ import annotations

import io
from collections import defaultdict
from typing import Any

from docling_core.transforms.chunker.tokenizer.base import BaseTokenizer
from vera_ingest.types import IngestBlock, IngestChunk, ParsedPage

from .options import DoclingOptions


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
        # captions is List[RefItem], not text — do not stringify refs.
        return str(getattr(item, "text", "") or getattr(item, "orig", "") or "")
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
