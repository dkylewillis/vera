from __future__ import annotations

import json
import sqlite3
from typing import Any

_CAPTION_MAX_GAP = 60.0


def figures(
    conn: sqlite3.Connection,
    page_start: int | None = None,
    page_end: int | None = None,
    include_data: bool = False,
) -> list[dict[str, Any]]:
    """Return extracted figures (image blocks + stored image assets)."""
    sql = """
        SELECT b.block_id, b.page_number, b.bbox_json,
               p.width AS page_width, p.height AS page_height,
               a.asset_id, a.mime_type, a.filename
        FROM blocks b
        JOIN pages p ON p.document_id = b.document_id AND p.page_number = b.page_number
        JOIN assets a ON a.asset_id = 'asset_' || b.block_id
        WHERE b.block_type = 'image'
    """
    params: list[Any] = []
    if page_start is not None:
        sql += " AND b.page_number >= ?"
        params.append(page_start)
    if page_end is not None:
        sql += " AND b.page_number <= ?"
        params.append(page_end)
    sql += " ORDER BY b.page_number, b.sort_order"
    rows = conn.execute(sql, params).fetchall()
    return _rows_to_figures(conn, rows, include_data)


def figures_for_chunk(
    conn: sqlite3.Connection,
    chunk_id: str,
    include_data: bool = False,
) -> list[dict[str, Any]]:
    """Return figures tightly linked to a specific chunk via ``chunk_blocks``.

    This is precise (only images the chunker actually associated with this
    chunk's text) rather than the coarser page-range lookup in :func:`figures`.
    """
    sql = """
        SELECT b.block_id, b.page_number, b.bbox_json,
               p.width AS page_width, p.height AS page_height,
               a.asset_id, a.mime_type, a.filename
        FROM chunk_blocks cb
        JOIN blocks b ON b.block_id = cb.block_id
        JOIN pages p ON p.document_id = b.document_id AND p.page_number = b.page_number
        JOIN assets a ON a.asset_id = 'asset_' || b.block_id
        WHERE cb.chunk_id = ? AND b.block_type = 'image'
        ORDER BY b.page_number, b.sort_order
    """
    rows = conn.execute(sql, (chunk_id,)).fetchall()
    return _rows_to_figures(conn, rows, include_data)


def _rows_to_figures(
    conn: sqlite3.Connection,
    rows: list[sqlite3.Row],
    include_data: bool,
) -> list[dict[str, Any]]:
    captions_by_page: dict[int, list[tuple[list[float] | None, str]]] = {}
    if rows:
        pages = sorted({row["page_number"] for row in rows})
        placeholders = ",".join("?" * len(pages))
        for cap in conn.execute(
            f"SELECT page_number, bbox_json, text FROM blocks "
            f"WHERE block_type = 'caption' AND page_number IN ({placeholders})",
            pages,
        ):
            bbox = json.loads(cap["bbox_json"]) if cap["bbox_json"] else None
            captions_by_page.setdefault(cap["page_number"], []).append((bbox, cap["text"]))
    results = []
    for row in rows:
        bbox = json.loads(row["bbox_json"]) if row["bbox_json"] else None
        figure = {
            "block_id": row["block_id"],
            "page_number": row["page_number"],
            "bbox": bbox,
            "page_width": row["page_width"],
            "page_height": row["page_height"],
            "asset_id": row["asset_id"],
            "mime_type": row["mime_type"],
            "filename": row["filename"],
            "caption": _nearest_caption(bbox, captions_by_page.get(row["page_number"], [])),
        }
        if include_data:
            figure["data"] = conn.execute(
                "SELECT data FROM assets WHERE asset_id = ?", (row["asset_id"],)
            ).fetchone()["data"]
        results.append(figure)
    return results


def figures_for_result(
    conn: sqlite3.Connection,
    result: Any,
    include_data: bool = False,
) -> list[dict[str, Any]]:
    """Return figures associated with a search result.

    Prefers figures directly linked to the result's chunk via ``chunk_blocks``
    (precise — the chunker only links an image when it co-occurs with the
    chunk's surrounding text). Falls back to a page-range lookup when no such
    link exists, e.g. for `.vera` files converted before this association was
    tracked.
    """
    chunk_id = getattr(result, "chunk_id", None)
    if chunk_id is not None:
        tight = figures_for_chunk(conn, chunk_id, include_data=include_data)
        if tight:
            return tight
    return figures(conn, result.page_start, result.page_end, include_data=include_data)


def _nearest_caption(
    bbox: list[float] | None,
    captions: list[tuple[list[float] | None, str]],
) -> str | None:
    if not captions:
        return None
    if bbox is None:
        return captions[0][1]
    best_text = None
    best_gap = _CAPTION_MAX_GAP
    for cap_bbox, text in captions:
        if cap_bbox is None:
            continue
        if cap_bbox[3] < bbox[1]:
            gap = bbox[1] - cap_bbox[3]
        elif bbox[3] < cap_bbox[1]:
            gap = cap_bbox[1] - bbox[3]
        else:
            gap = 0.0
        if gap <= best_gap:
            best_gap = gap
            best_text = text
    return best_text
