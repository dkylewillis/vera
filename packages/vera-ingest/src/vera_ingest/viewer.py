"""Read ingest-produced viewer metadata from a VERA archive.

``vera-doc`` stores opaque chunks and attachments. This module interprets the
attachment and metadata conventions written by :mod:`vera_ingest.convert`:

- archive metadata keys ``viewer_pages_attachment_id``,
  ``viewer_blocks_attachment_id``, and ``source_attachment_id``
- figure attachments with ``metadata.role == "figure"``
- chunk metadata ``regions`` for visual grounding
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from vera_doc import AttachmentRecord, QueryResult, VeraDocument
from vera_doc.models import thaw_json


def get_source_document(document: VeraDocument) -> AttachmentRecord:
    """Return the attachment identified as the archive's source document."""
    attachment_id = document.metadata.get("source_attachment_id")
    if not attachment_id:
        raise ValueError("Original source document is not stored in this archive")
    return document.get_attachment(str(attachment_id))


def result_payload(result: QueryResult) -> dict[str, Any]:
    """Flatten a search hit for CLI/MCP JSON (metadata keys at the top level)."""
    data = result.as_dict()
    metadata = data.pop("metadata", {})
    payload = {**metadata, **data}
    for key in ("before_chunks", "after_chunks"):
        if key in payload:
            payload[key] = [{**item.pop("metadata", {}), **item} for item in payload[key]]
    return payload


def _safe_stored_filename(stored: str | None) -> str:
    """Return a basename-only stored filename, rejecting traversal."""
    raw = stored or "source_document"
    candidate = Path(raw)
    if candidate.is_absolute() or any(part == ".." for part in candidate.parts):
        raise ValueError(f"Stored source filename {raw!r} is not a safe relative name")
    name = candidate.name
    if not name or name in {".", ".."}:
        raise ValueError(f"Stored source filename {raw!r} is not a safe relative name")
    return name


def _confine_to_directory(target: Path, root: Path) -> Path:
    resolved_root = root.resolve()
    resolved = target.resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError(f"Export path {str(target)!r} is outside the allowed directory")
    return resolved


def export_source_document(
    document: VeraDocument,
    path: str | os.PathLike[str] | None = None,
) -> str:
    """Write the source attachment to disk and return its path.

    The stored filename is used as ``Path(...).name`` only. Absolute names and
    ``..`` segments are rejected. When ``path`` is omitted the file is written
    under the current working directory; when ``path`` is a directory the file
    stays under that directory. An explicit file path is the caller's chosen
    output location.
    """
    source = get_source_document(document)
    filename = _safe_stored_filename(source.filename)
    if path is None:
        root = Path.cwd()
        target = _confine_to_directory(root / filename, root)
    else:
        specified = Path(path)
        if specified.is_dir():
            target = _confine_to_directory(specified / filename, specified)
        else:
            target = specified
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.data)
    return str(target)


def get_page(document: VeraDocument, page_number: int) -> dict[str, Any] | None:
    """Return ingest-provided viewer data for one page."""
    for page in _viewer_payload(document, "viewer_pages_attachment_id"):
        if page.get("page_number") == page_number:
            return {"page_id": f"page_{page_number:06d}", **page}
    return None


def get_blocks(
    document: VeraDocument,
    page_number: int | None = None,
) -> list[dict[str, Any]]:
    """Return ingest-provided layout blocks."""
    blocks = _viewer_payload(document, "viewer_blocks_attachment_id")
    if page_number is None:
        return blocks
    return [block for block in blocks if block.get("page_number") == page_number]


def get_chunk_regions(document: VeraDocument, chunk_id: str) -> list[dict[str, Any]]:
    """Return ingest-provided highlight regions for a chunk."""
    records = document.get([chunk_id])
    if not records:
        return []
    return list(thaw_json(records[0].metadata).get("regions", []))


def regions_for(document: VeraDocument, result: QueryResult) -> list[dict[str, Any]]:
    """Return ingest-provided highlight regions for a query result."""
    return get_chunk_regions(document, result.record.id)


def figures(
    document: VeraDocument,
    page_start: int | None = None,
    page_end: int | None = None,
    include_data: bool = False,
    attachment_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Return figure attachments produced during ingest."""
    attachments = document.attachment_metadata(
        attachment_ids,
        where={"role": "figure"},
    )
    if not attachments:
        return []
    pages = {
        page["page_number"]: page
        for page in _viewer_payload(document, "viewer_pages_attachment_id")
    }
    caption_blocks = [
        block
        for block in _viewer_payload(document, "viewer_blocks_attachment_id")
        if block.get("block_type") == "caption"
    ]
    results: list[dict[str, Any]] = []
    for attachment in attachments:
        metadata = thaw_json(attachment["metadata"])
        page_number = metadata.get("page_number")
        if page_start is not None and page_number is not None and page_number < page_start:
            continue
        if page_end is not None and page_number is not None and page_number > page_end:
            continue
        page = pages.get(page_number, {})
        bbox = metadata.get("bbox")
        figure: dict[str, Any] = {
            "block_id": attachment["id"].removeprefix("image_"),
            "page_number": page_number,
            "bbox": bbox,
            "page_width": page.get("width"),
            "page_height": page.get("height"),
            "asset_id": attachment["id"],
            "mime_type": attachment["media_type"],
            "filename": attachment["filename"],
            "caption": _caption_for_figure(caption_blocks, page_number, bbox),
        }
        if include_data:
            figure["data"] = document.get_attachment(attachment["id"]).data
        results.append(figure)
    return results


def figures_for(
    document: VeraDocument,
    result: QueryResult,
    include_data: bool = False,
) -> list[dict[str, Any]]:
    """Return figure attachments linked to a query result."""
    attachment_ids = {
        ref.attachment_id for ref in result.record.attachments if ref.role == "figure"
    }
    return figures(
        document,
        include_data=include_data,
        attachment_ids=sorted(attachment_ids),
    )


def _caption_for_figure(
    caption_blocks: list[dict[str, Any]],
    page_number: Any,
    bbox: Any,
) -> str | None:
    """Pick the caption on the same page nearest below the figure bbox."""
    candidates = [block for block in caption_blocks if block.get("page_number") == page_number]
    if not candidates:
        return None
    if len(candidates) == 1 or not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return candidates[0].get("text")
    figure_bottom = float(bbox[3])

    def sort_key(block: dict[str, Any]) -> tuple[float, float]:
        box = block.get("bbox") or ()
        if not isinstance(box, (list, tuple)) or len(box) < 2:
            return (float("inf"), float("inf"))
        below = float(box[1]) - figure_bottom
        return (0.0 if below >= 0 else 1.0, abs(below))

    return min(candidates, key=sort_key).get("text")


def _viewer_payload(document: VeraDocument, metadata_key: str) -> list[dict[str, Any]]:
    attachment_id = document.metadata.get(metadata_key)
    if not attachment_id:
        return []
    attachment = document.get_attachment(str(attachment_id))
    payload = json.loads(attachment.data)
    return payload if isinstance(payload, list) else []
