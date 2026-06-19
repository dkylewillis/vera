from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SourceDocument:
    """The original source document stored inside a VERA file."""

    filename: str | None
    mime_type: str | None
    data: bytes
    hash: str | None


def get_source_document(conn: sqlite3.Connection) -> SourceDocument:
    """Return the original source document stored in this VERA file."""
    row = conn.execute(
        "SELECT filename, mime_type, data, hash FROM assets WHERE asset_type = 'original_document'"
    ).fetchone()
    if row is None or row["data"] is None:
        raise ValueError("No original document stored in this VERA file")
    return SourceDocument(
        filename=row["filename"],
        mime_type=row["mime_type"],
        data=row["data"],
        hash=row["hash"],
    )


def export_source_document(conn: sqlite3.Connection, path: str | None = None) -> str:
    """Write the original source document to disk and return its path."""
    source = get_source_document(conn)
    fallback = source.filename or "source_document"
    target = Path(path) if path else Path(fallback)
    if target.is_dir():
        target = target / fallback
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.data)
    return str(target)


def get_page(conn: sqlite3.Connection, page_number: int) -> dict[str, Any] | None:
    """Return a single page (1-based) with its text and dimensions, or None."""
    row = conn.execute(
        "SELECT page_id, page_number, width, height, text FROM pages WHERE page_number = ?",
        (page_number,),
    ).fetchone()
    return dict(row) if row is not None else None


def get_blocks(conn: sqlite3.Connection, page_number: int | None = None) -> list[dict[str, Any]]:
    """Return layout blocks in reading order, optionally for a single page."""
    sql = """
        SELECT block_id, page_number, block_type, text, bbox_json, heading_level, sort_order
        FROM blocks
    """
    params: list[Any] = []
    if page_number is not None:
        sql += " WHERE page_number = ?"
        params.append(page_number)
    sql += " ORDER BY sort_order"
    blocks = []
    for row in conn.execute(sql, params):
        block = dict(row)
        bbox_json = block.pop("bbox_json")
        block["bbox"] = json.loads(bbox_json) if bbox_json else None
        blocks.append(block)
    return blocks


def get_asset(conn: sqlite3.Connection, asset_id: str, include_data: bool = True) -> dict[str, Any] | None:
    """Return a stored asset by id (image, original document, ...), or None."""
    row = conn.execute(
        "SELECT asset_id, document_id, asset_type, mime_type, filename, data, hash FROM assets WHERE asset_id = ?",
        (asset_id,),
    ).fetchone()
    if row is None:
        return None
    asset = dict(row)
    if not include_data:
        asset.pop("data")
    return asset


def get_chunk_regions(conn: sqlite3.Connection, chunk_id: str) -> list[dict[str, Any]]:
    """Return the page regions (bounding boxes) a chunk's text came from."""
    rows = conn.execute(
        """
        SELECT b.block_id, b.page_number, b.bbox_json, p.width AS page_width, p.height AS page_height
        FROM chunk_blocks cb
        JOIN blocks b ON b.block_id = cb.block_id
        LEFT JOIN pages p ON p.page_id = b.page_id
        WHERE cb.chunk_id = ?
        ORDER BY b.sort_order
        """,
        (chunk_id,),
    ).fetchall()
    regions = []
    for row in rows:
        regions.append(
            {
                "block_id": row["block_id"],
                "page_number": row["page_number"],
                "bbox": json.loads(row["bbox_json"]) if row["bbox_json"] else None,
                "page_width": row["page_width"],
                "page_height": row["page_height"],
            }
        )
    return regions


def regions_for_result(conn: sqlite3.Connection, result: Any) -> list[dict[str, Any]]:
    """Return highlight regions for a search result."""
    return get_chunk_regions(conn, result.chunk_id)
