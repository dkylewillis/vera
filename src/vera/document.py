from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.figures import figures as get_figures
from .core.figures import figures_for_result
from .core.search import SearchResult, context_chunks_for, search_document
from .core.validation import validate_document


@dataclass
class SourceDocument:
    """The original source document stored inside a VERA file."""

    filename: str | None
    mime_type: str | None
    data: bytes
    hash: str | None


class VeraDocument:
    def __init__(self, path: str, conn: sqlite3.Connection):
        self.path = path
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    @classmethod
    def open(cls, path: str) -> "VeraDocument":
        conn = sqlite3.connect(path)
        return cls(path, conn)

    def close(self) -> None:
        self.conn.close()

    def inspect(self) -> dict[str, Any]:
        metadata = {row["key"]: row["value"] for row in self.conn.execute("SELECT key, value FROM vera_metadata")}
        doc = self.conn.execute("SELECT * FROM documents LIMIT 1").fetchone()
        metadata.update(
            {
                "file": self.path,
                "source": doc["source_filename"] if doc else None,
                "pages": self.conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0],
                "chunks": self.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
                "embeddings": self.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0],
            }
        )
        return metadata

    def validate(self) -> dict[str, Any]:
        return validate_document(self.conn)

    def figures(
        self,
        page_start: int | None = None,
        page_end: int | None = None,
        include_data: bool = False,
    ) -> list[dict[str, Any]]:
        """Return extracted figures (image blocks + stored image assets).

        Each figure includes its caption text when a caption block sits
        vertically adjacent on the same page. Optionally filter to a page
        range, e.g. the pages of a search result. Set include_data=True to
        also return the image bytes.
        """
        return get_figures(self.conn, page_start, page_end, include_data=include_data)

    def figures_for(self, result: SearchResult, include_data: bool = False) -> list[dict[str, Any]]:
        """Return figures located on the pages of a search result."""
        return figures_for_result(self.conn, result, include_data=include_data)

    def get_source_document(self) -> SourceDocument:
        """Return the original source document (e.g. the PDF) stored in this file.

        Raises ValueError if the file was created with store_original=False.
        """
        row = self.conn.execute(
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

    def export_source_document(self, path: str | None = None) -> str:
        """Write the original source document to disk and return its path.

        When path is omitted, the stored source filename is used in the
        current working directory. When path is an existing directory, the
        stored filename is written inside it.
        """
        source = self.get_source_document()
        fallback = source.filename or "source_document"
        target = Path(path) if path else Path(fallback)
        if target.is_dir():
            target = target / fallback
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.data)
        return str(target)

    def get_page(self, page_number: int) -> dict[str, Any] | None:
        """Return a single page (1-based) with its text and dimensions, or None."""
        row = self.conn.execute(
            "SELECT page_id, page_number, width, height, text FROM pages WHERE page_number = ?",
            (page_number,),
        ).fetchone()
        return dict(row) if row is not None else None

    def get_blocks(self, page_number: int | None = None) -> list[dict[str, Any]]:
        """Return layout blocks in reading order, optionally for a single page.

        Each block carries its bbox ([x0, y0, x1, y1] in page points, origin
        top-left) so applications can render page overlays.
        """
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
        for row in self.conn.execute(sql, params):
            block = dict(row)
            bbox_json = block.pop("bbox_json")
            block["bbox"] = json.loads(bbox_json) if bbox_json else None
            blocks.append(block)
        return blocks

    def get_asset(self, asset_id: str, include_data: bool = True) -> dict[str, Any] | None:
        """Return a stored asset by id (image, original document, ...), or None."""
        row = self.conn.execute(
            "SELECT asset_id, document_id, asset_type, mime_type, filename, data, hash FROM assets WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        asset = dict(row)
        if not include_data:
            asset.pop("data")
        return asset

    def get_chunk_regions(self, chunk_id: str) -> list[dict[str, Any]]:
        """Return the page regions (bounding boxes) a chunk's text came from.

        Each region is one contributing block: {page_number, bbox, block_id,
        page_width, page_height}. bbox is [x0, y0, x1, y1] in page points with
        the origin at the top-left; page dimensions let viewers scale the box
        to any rendered size. Regions are block-granular: a chunk that starts
        or ends mid-block highlights the whole block.
        """
        rows = self.conn.execute(
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

    def regions_for(self, result: SearchResult) -> list[dict[str, Any]]:
        """Return highlight regions for a search result (see get_chunk_regions)."""
        return self.get_chunk_regions(result.chunk_id)

    def search(self, query: str, mode: str = "hybrid", top_k: int = 10, context_chunks: int = 0) -> list[SearchResult]:
        return search_document(self.conn, query, mode=mode, top_k=top_k, context_chunks=context_chunks)

    def _context_chunks_for(self, chunk_id: str, context_chunks: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        return context_chunks_for(self.conn, chunk_id, context_chunks)
