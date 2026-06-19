from __future__ import annotations

import sqlite3
from typing import Any

from .core.access import SourceDocument
from .core.access import export_source_document as export_source
from .core.access import get_asset as get_stored_asset
from .core.access import get_blocks as get_layout_blocks
from .core.access import get_chunk_regions as get_regions
from .core.access import get_page as get_stored_page
from .core.access import get_source_document as get_stored_source_document
from .core.access import regions_for_result
from .core.figures import figures as get_figures
from .core.figures import figures_for_result
from .core.inspection import inspect_document
from .core.search import SearchResult, search_document
from .core.validation import validate_document


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
        return inspect_document(self.conn, self.path)

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
        return get_stored_source_document(self.conn)

    def export_source_document(self, path: str | None = None) -> str:
        """Write the original source document to disk and return its path.

        When path is omitted, the stored source filename is used in the
        current working directory. When path is an existing directory, the
        stored filename is written inside it.
        """
        return export_source(self.conn, path)

    def get_page(self, page_number: int) -> dict[str, Any] | None:
        """Return a single page (1-based) with its text and dimensions, or None."""
        return get_stored_page(self.conn, page_number)

    def get_blocks(self, page_number: int | None = None) -> list[dict[str, Any]]:
        """Return layout blocks in reading order, optionally for a single page.

        Each block carries its bbox ([x0, y0, x1, y1] in page points, origin
        top-left) so applications can render page overlays.
        """
        return get_layout_blocks(self.conn, page_number)

    def get_asset(self, asset_id: str, include_data: bool = True) -> dict[str, Any] | None:
        """Return a stored asset by id (image, original document, ...), or None."""
        return get_stored_asset(self.conn, asset_id, include_data=include_data)

    def get_chunk_regions(self, chunk_id: str) -> list[dict[str, Any]]:
        """Return the page regions (bounding boxes) a chunk's text came from.

        Each region is one contributing block: {page_number, bbox, block_id,
        page_width, page_height}. bbox is [x0, y0, x1, y1] in page points with
        the origin at the top-left; page dimensions let viewers scale the box
        to any rendered size. Regions are block-granular: a chunk that starts
        or ends mid-block highlights the whole block.
        """
        return get_regions(self.conn, chunk_id)

    def regions_for(self, result: SearchResult) -> list[dict[str, Any]]:
        """Return highlight regions for a search result (see get_chunk_regions)."""
        return regions_for_result(self.conn, result)

    def search(self, query: str, mode: str = "hybrid", top_k: int = 10, context_chunks: int = 0) -> list[SearchResult]:
        return search_document(self.conn, query, mode=mode, top_k=top_k, context_chunks=context_chunks)
