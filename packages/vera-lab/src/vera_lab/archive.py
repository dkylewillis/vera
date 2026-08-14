"""Load a lab document from an existing .vera archive."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from vera_doc import VeraDocument
from vera_doc.models import thaw_json
from vera_ingest.viewer import figures, get_blocks, get_chunk_regions, get_source_document
from vera_lab.model import LabBlock, LabChunk, LabDocument, LabFigure, LabPage, LabRegion


def load_archive_document(archive_path: str | Path) -> LabDocument:
    """Build a :class:`LabDocument` from a written ``.vera`` archive."""
    path = Path(archive_path)
    if not path.is_file():
        raise FileNotFoundError(f"Archive not found: {path}")
    document = VeraDocument.open(path)
    try:
        source = get_source_document(document)
        source_bytes = source.data
        archive_meta = document.metadata
        page_rows = _viewer_pages(document)
        pages = [
            LabPage(
                page_number=int(row["page_number"]),
                width=row.get("width"),
                height=row.get("height"),
                text=str(row.get("text") or ""),
            )
            for row in page_rows
        ]
        page_dimensions = {page.page_number: (page.width, page.height) for page in pages}
        blocks = [
            LabBlock(
                block_id=str(row["block_id"]),
                page_number=int(row["page_number"]),
                block_type=str(row.get("block_type") or "paragraph"),
                text=str(row.get("text") or ""),
                bbox=list(row["bbox"]) if row.get("bbox") else None,
                heading_level=row.get("heading_level"),
                sort_order=int(row.get("sort_order") or 0),
                has_image=False,
            )
            for row in get_blocks(document)
        ]
        block_ids_by_chunk = _block_ids_from_regions_and_attachments(document)
        chunks: list[LabChunk] = []
        for record in document.get():
            metadata = thaw_json(record.metadata)
            regions_raw = get_chunk_regions(document, record.id)
            regions = [
                LabRegion(
                    block_id=str(item.get("block_id") or ""),
                    page_number=int(item["page_number"]),
                    bbox=list(item["bbox"]),
                    page_width=item.get("page_width"),
                    page_height=item.get("page_height"),
                )
                for item in regions_raw
                if item.get("bbox")
            ]
            linked = block_ids_by_chunk.get(record.id, [])
            if not linked:
                linked = [region.block_id for region in regions if region.block_id]
            chunks.append(
                LabChunk(
                    chunk_id=record.id,
                    text=record.text,
                    page_start=int(metadata.get("page_start") or 1),
                    page_end=int(metadata.get("page_end") or metadata.get("page_start") or 1),
                    heading_path=str(metadata.get("heading_path") or ""),
                    token_count=int(metadata.get("token_count") or len(record.text.split())),
                    block_ids=linked,
                    regions=regions,
                )
            )
        figure_rows = figures(document, include_data=True)
        lab_figures: list[LabFigure] = []
        for row in figure_rows:
            data = row.get("data")
            data_url = None
            if data is not None:
                mime = row.get("mime_type") or "application/octet-stream"
                data_url = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
            page_number = int(row["page_number"]) if row.get("page_number") is not None else 1
            width, height = page_dimensions.get(page_number, (None, None))
            lab_figures.append(
                LabFigure(
                    block_id=str(row.get("block_id") or ""),
                    page_number=page_number,
                    bbox=list(row["bbox"]) if row.get("bbox") else None,
                    page_width=row.get("page_width", width),
                    page_height=row.get("page_height", height),
                    mime_type=row.get("mime_type"),
                    filename=row.get("filename"),
                    caption=row.get("caption"),
                    data_url=data_url,
                )
            )
            for block in blocks:
                if block.block_id == str(row.get("block_id") or ""):
                    block.has_image = True
        return LabDocument(
            source_path=str(path),
            source_bytes=source_bytes,
            pages=pages,
            blocks=blocks,
            chunks=chunks,
            figures=lab_figures,
            parser_name=str(archive_meta.get("parser_name") or ""),
            parser_version=str(archive_meta.get("parser_version") or ""),
            chunking_strategy=str(archive_meta.get("chunking_strategy") or ""),
            diagnostics=dict(archive_meta.get("ocr") or {}),
            pipeline_spec=str(archive_meta.get("parser_name") or ""),
            pipeline_options={},
            mode="archive",
        )
    finally:
        document.close()


def _viewer_pages(document: VeraDocument) -> list[dict[str, Any]]:
    from vera_ingest.viewer import get_page

    page_count = int(document.metadata.get("page_count") or 0)
    pages: list[dict[str, Any]] = []
    for page_number in range(1, page_count + 1):
        page = get_page(document, page_number)
        if page is not None:
            pages.append(page)
    return pages


def _block_ids_from_regions_and_attachments(document: VeraDocument) -> dict[str, list[str]]:
    """Best-effort chunk -> block_ids from regions and figure attachment refs."""
    mapping: dict[str, list[str]] = {}
    for record in document.get():
        ids: list[str] = []
        for region in thaw_json(record.metadata).get("regions", []):
            block_id = region.get("block_id")
            if block_id and block_id not in ids:
                ids.append(str(block_id))
        for ref in record.attachments:
            if ref.role == "figure":
                block_id = ref.attachment_id.removeprefix("image_")
                if block_id and block_id not in ids:
                    ids.append(block_id)
        mapping[record.id] = ids
    return mapping
