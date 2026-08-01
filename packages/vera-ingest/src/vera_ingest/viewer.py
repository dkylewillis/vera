"""Read extractor-produced viewer metadata from a VERA archive.

``vera-doc`` stores opaque chunks and attachments. This module interprets the
attachment and metadata conventions written by :mod:`vera_extract.convert`:

- archive metadata keys ``viewer_pages_attachment_id``,
  ``viewer_blocks_attachment_id``, and ``source_attachment_id``
- figure attachments with ``metadata.role == "figure"``
- chunk metadata ``regions`` for visual grounding
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vera import AttachmentRecord, QueryResult, VeraDocument
from vera.models import thaw_json


def get_source_document(document: VeraDocument) -> AttachmentRecord:
    """Return the attachment identified as the archive's source document."""
    attachment_id = document.metadata.get("source_attachment_id")
    if not attachment_id:
        raise ValueError("No source document is stored in this VERA file")
    return document.get_attachment(str(attachment_id))


def export_source_document(
    document: VeraDocument,
    path: str | os.PathLike[str] | None = None,
) -> str:
    """Write the source attachment to disk and return its path."""
    source = get_source_document(document)
    fallback = source.filename or "source_document"
    target = Path(path) if path is not None else Path(fallback)
    if target.is_dir():
        target = target / fallback
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.data)
    return str(target)


def get_page(document: VeraDocument, page_number: int) -> dict[str, Any] | None:
    """Return extractor-provided viewer data for one page."""
    for page in _viewer_payload(document, "viewer_pages_attachment_id"):
        if page.get("page_number") == page_number:
            return {"page_id": f"page_{page_number:06d}", **page}
    return None


def get_blocks(
    document: VeraDocument,
    page_number: int | None = None,
) -> list[dict[str, Any]]:
    """Return extractor-provided layout blocks."""
    blocks = _viewer_payload(document, "viewer_blocks_attachment_id")
    if page_number is None:
        return blocks
    return [
        block
        for block in blocks
        if block.get("page_number") == page_number
    ]


def get_chunk_regions(document: VeraDocument, chunk_id: str) -> list[dict[str, Any]]:
    """Return extractor-provided highlight regions for a chunk."""
    records = document.get([chunk_id])
    if not records:
        return []
    return list(thaw_json(records[0].metadata).get("regions", []))


def regions_for(document: VeraDocument, result: QueryResult) -> list[dict[str, Any]]:
    """Return extractor-provided highlight regions for a query result."""
    return get_chunk_regions(document, result.record.id)


def figures(
    document: VeraDocument,
    page_start: int | None = None,
    page_end: int | None = None,
    include_data: bool = False,
) -> list[dict[str, Any]]:
    """Return figure attachments produced by an extractor."""
    pages = {
        page["page_number"]: page
        for page in _viewer_payload(document, "viewer_pages_attachment_id")
    }
    captions = {
        block["page_number"]: block["text"]
        for block in _viewer_payload(document, "viewer_blocks_attachment_id")
        if block.get("block_type") == "caption"
    }
    results: list[dict[str, Any]] = []
    for attachment in document.attachments(where={"role": "figure"}):
        metadata = thaw_json(attachment.metadata)
        page_number = metadata.get("page_number")
        if (
            page_start is not None
            and page_number is not None
            and page_number < page_start
        ):
            continue
        if (
            page_end is not None
            and page_number is not None
            and page_number > page_end
        ):
            continue
        page = pages.get(page_number, {})
        figure: dict[str, Any] = {
            "block_id": attachment.id.removeprefix("image_"),
            "page_number": page_number,
            "bbox": metadata.get("bbox"),
            "page_width": page.get("width"),
            "page_height": page.get("height"),
            "asset_id": attachment.id,
            "mime_type": attachment.media_type,
            "filename": attachment.filename,
            "caption": captions.get(page_number),
        }
        if include_data:
            figure["data"] = attachment.data
        results.append(figure)
    return results


def figures_for(
    document: VeraDocument,
    result: QueryResult,
    include_data: bool = False,
) -> list[dict[str, Any]]:
    """Return figure attachments linked to a query result."""
    attachment_ids = {
        ref.attachment_id
        for ref in result.record.attachments
        if ref.role == "figure"
    }
    return [
        figure
        for figure in figures(document, include_data=include_data)
        if figure["asset_id"] in attachment_ids
    ]


def _viewer_payload(document: VeraDocument, metadata_key: str) -> list[dict[str, Any]]:
    attachment_id = document.metadata.get(metadata_key)
    if not attachment_id:
        return []
    attachment = document.get_attachment(str(attachment_id))
    payload = json.loads(attachment.data)
    return payload if isinstance(payload, list) else []
