from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .core.schema import FORMAT_VERSION
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
from .database import VeraDatabase
from .models import QueryResult, thaw_json


class VeraDocument:
    """Read-oriented facade for an existing ``.vera`` archive.

    Prefer :class:`~vera.database.VeraDatabase` for CRUD. ``VeraDocument`` adds
    figure listing, page access, highlight regions, and source export on top
    of search. Used by the CLI, desktop app, and MCP adapter.

    Example:
        ```python
        from vera import VeraDocument

        with VeraDocument.open("manual.vera") as document:
            for result in document.search("detention requirements", top_k=5):
                print(result.page_start, result.heading_path, result.text)
        ```
    """

    def __init__(
        self,
        path: str,
        conn: sqlite3.Connection | None,
        *,
        database: VeraDatabase | None = None,
    ):
        self.path = path
        self.conn = conn
        self._database = database
        if self.conn is not None:
            self.conn.row_factory = sqlite3.Row

    @classmethod
    def open(cls, path: str) -> "VeraDocument":
        """Open an existing ``.vera`` archive for read-only access.

        Args:
            path: Path to a ``.vera`` file.

        Returns:
            A document handle.

        Raises:
            FileNotFoundError: When ``path`` does not exist.
        """
        if not Path(path).is_file():
            raise FileNotFoundError(path)
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT value FROM vera_metadata WHERE key = 'format_version'"
            ).fetchone()
            if row is not None and row["value"] == FORMAT_VERSION:
                conn.close()
                return cls(
                    path,
                    None,
                    database=VeraDatabase.open(path, mode="read"),
                )
        except sqlite3.Error:
            return cls(path, conn)
        return cls(path, conn)

    def close(self) -> None:
        if self._database is not None:
            self._database.close()
        elif self.conn is not None:
            self.conn.close()

    def __enter__(self) -> "VeraDocument":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def inspect(self) -> dict[str, Any]:
        if self._database is not None:
            info = self._database.inspect()
            metadata = info.pop("metadata")
            return {
                **metadata,
                **info,
                "source": metadata.get("source_file_name"),
                "pages": metadata.get("page_count", 0),
                "default_embedding_model": info.get("embedding_model"),
                "default_embedding_dimension": info.get("embedding_dimension"),
            }
        assert self.conn is not None
        return inspect_document(self.conn, self.path)

    def validate(self) -> dict[str, Any]:
        if self._database is not None:
            return self._database.validate()
        assert self.conn is not None
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
        if self._database is not None:
            return self._modern_figures(
                page_start=page_start,
                page_end=page_end,
                include_data=include_data,
            )
        assert self.conn is not None
        return get_figures(self.conn, page_start, page_end, include_data=include_data)

    def figures_for(self, result: SearchResult, include_data: bool = False) -> list[dict[str, Any]]:
        """Return figures located on the pages of a search result."""
        if self._database is not None:
            record = self._database.get([result.chunk_id])
            attachment_ids = {
                ref.attachment_id
                for ref in (record[0].attachments if record else ())
                if ref.role == "figure"
            }
            return [
                figure
                for figure in self._modern_figures(include_data=include_data)
                if figure["asset_id"] in attachment_ids
            ]
        assert self.conn is not None
        return figures_for_result(self.conn, result, include_data=include_data)

    def get_source_document(self) -> SourceDocument:
        """Return the original source document (e.g. the PDF) stored in this file.

        Raises ValueError if the file was created with store_original=False.
        """
        if self._database is not None:
            attachment_id = self._database.metadata.get("source_attachment_id")
            if not attachment_id:
                raise ValueError("No original document stored in this VERA file")
            attachment = self._database.get_attachment(attachment_id)
            return SourceDocument(
                filename=attachment.filename,
                mime_type=attachment.media_type,
                data=attachment.data,
                hash=attachment.checksum,
            )
        assert self.conn is not None
        return get_stored_source_document(self.conn)

    def export_source_document(self, path: str | None = None) -> str:
        """Write the original source document to disk and return its path.

        When path is omitted, the stored source filename is used in the
        current working directory. When path is an existing directory, the
        stored filename is written inside it.
        """
        if self._database is not None:
            source = self.get_source_document()
            fallback = source.filename or "source_document"
            target = Path(path) if path else Path(fallback)
            if target.is_dir():
                target = target / fallback
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.data)
            return str(target)
        assert self.conn is not None
        return export_source(self.conn, path)

    def get_page(self, page_number: int) -> dict[str, Any] | None:
        """Return a single page (1-based) with its text and dimensions, or None."""
        if self._database is not None:
            pages = self._viewer_payload("viewer_pages_attachment_id")
            for page in pages:
                if page.get("page_number") == page_number:
                    return {
                        "page_id": f"page_{page_number:06d}",
                        **page,
                    }
            return None
        assert self.conn is not None
        return get_stored_page(self.conn, page_number)

    def get_blocks(self, page_number: int | None = None) -> list[dict[str, Any]]:
        """Return layout blocks in reading order, optionally for a single page.

        Each block carries its bbox ([x0, y0, x1, y1] in page points, origin
        top-left) so applications can render page overlays.
        """
        if self._database is not None:
            blocks = self._viewer_payload("viewer_blocks_attachment_id")
            if page_number is not None:
                blocks = [
                    block
                    for block in blocks
                    if block.get("page_number") == page_number
                ]
            return blocks
        assert self.conn is not None
        return get_layout_blocks(self.conn, page_number)

    def get_asset(self, asset_id: str, include_data: bool = True) -> dict[str, Any] | None:
        """Return a stored asset by id (image, original document, ...), or None."""
        if self._database is not None:
            if asset_id == "asset_original_001":
                modern_id = str(
                    self._database.metadata.get(
                        "source_attachment_id",
                        "source_original",
                    )
                )
            elif asset_id.startswith("asset_block_"):
                modern_id = f"image_{asset_id.removeprefix('asset_')}"
            else:
                modern_id = asset_id
            try:
                attachment = self._database.get_attachment(modern_id)
            except KeyError:
                return None
            result = {
                "asset_id": asset_id,
                "asset_type": (
                    "original_document"
                    if asset_id == "asset_original_001"
                    else attachment.metadata.get("role", "attachment")
                ),
                "mime_type": attachment.media_type,
                "filename": attachment.filename,
                "hash": attachment.checksum,
                "metadata": thaw_json(attachment.metadata),
            }
            if include_data:
                result["data"] = attachment.data
            return result
        assert self.conn is not None
        return get_stored_asset(self.conn, asset_id, include_data=include_data)

    def get_chunk_regions(self, chunk_id: str) -> list[dict[str, Any]]:
        """Return the page regions (bounding boxes) a chunk's text came from.

        Each region is one contributing block: {page_number, bbox, block_id,
        page_width, page_height}. bbox is [x0, y0, x1, y1] in page points with
        the origin at the top-left; page dimensions let viewers scale the box
        to any rendered size. Regions are block-granular: a chunk that starts
        or ends mid-block highlights the whole block.
        """
        if self._database is not None:
            records = self._database.get([chunk_id])
            return (
                list(thaw_json(records[0].metadata).get("regions", []))
                if records
                else []
            )
        assert self.conn is not None
        return get_regions(self.conn, chunk_id)

    def regions_for(self, result: SearchResult) -> list[dict[str, Any]]:
        """Return highlight regions for a search result (see get_chunk_regions)."""
        if self._database is not None:
            return self.get_chunk_regions(result.chunk_id)
        assert self.conn is not None
        return regions_for_result(self.conn, result)

    def search(self, query: str, mode: str = "hybrid", top_k: int = 10, context_chunks: int = 0) -> list[SearchResult]:
        """Search the archive and return citation-ready results.

        Args:
            query: Query string.
            mode: ``"hybrid"`` (default), ``"semantic"``, or ``"keyword"``.
            top_k: Maximum number of results.
            context_chunks: Number of neighboring chunks to include before and
                after each hit.

        Returns:
            Ranked :class:`~vera.core.search.SearchResult` objects.
        """
        if context_chunks < 0:
            raise ValueError("context_chunks must be non-negative")
        if self._database is not None:
            results = self._database.search(
                text=query,
                mode=mode,  # type: ignore[arg-type]
                top_k=top_k,
            )
            mapped = [self._legacy_result(result) for result in results]
            if context_chunks:
                all_records = self._database.get()
                positions = {
                    record.id: index for index, record in enumerate(all_records)
                }
                for result in mapped:
                    position = positions[result.chunk_id]
                    result.before_chunks = [
                        self._context_record(record)
                        for record in all_records[
                            max(0, position - context_chunks):position
                        ]
                    ]
                    result.after_chunks = [
                        self._context_record(record)
                        for record in all_records[
                            position + 1:position + context_chunks + 1
                        ]
                    ]
            return mapped
        assert self.conn is not None
        return search_document(self.conn, query, mode=mode, top_k=top_k, context_chunks=context_chunks)

    def _viewer_payload(self, metadata_key: str) -> list[dict[str, Any]]:
        assert self._database is not None
        attachment_id = self._database.metadata.get(metadata_key)
        if not attachment_id:
            return []
        attachment = self._database.get_attachment(attachment_id)
        payload = json.loads(attachment.data)
        return payload if isinstance(payload, list) else []

    def _modern_figures(
        self,
        page_start: int | None = None,
        page_end: int | None = None,
        include_data: bool = False,
    ) -> list[dict[str, Any]]:
        assert self._database is not None
        rows = self._database._conn.execute(
            """
            SELECT attachment_id FROM attachments
            WHERE json_extract(metadata_json, '$.role') = 'figure'
            ORDER BY attachment_id
            """
        ).fetchall()
        pages = {
            page["page_number"]: page
            for page in self._viewer_payload("viewer_pages_attachment_id")
        }
        blocks = self._viewer_payload("viewer_blocks_attachment_id")
        captions = {
            block["page_number"]: block["text"]
            for block in blocks
            if block.get("block_type") == "caption"
        }
        results = []
        for row in rows:
            attachment = self._database.get_attachment(row["attachment_id"])
            metadata = thaw_json(attachment.metadata)
            page_number = metadata.get("page_number")
            if page_start is not None and page_number < page_start:
                continue
            if page_end is not None and page_number > page_end:
                continue
            block_id = attachment.id.removeprefix("image_")
            page = pages.get(page_number, {})
            figure = {
                "block_id": block_id,
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

    @staticmethod
    def _legacy_result(result: QueryResult) -> SearchResult:
        metadata = thaw_json(result.record.metadata)
        return SearchResult(
            chunk_id=result.record.id,
            score=result.score,
            text=result.record.text,
            page_start=metadata.get("page_start"),
            page_end=metadata.get("page_end"),
            heading_path=metadata.get("heading_path"),
            source_filename=metadata.get("source_filename"),
            document_id=metadata.get("document_id", "document_0001"),
        )

    @staticmethod
    def _context_record(record: Any) -> dict[str, Any]:
        metadata = thaw_json(record.metadata)
        return {
            "chunk_id": record.id,
            "text": record.text,
            "page_start": metadata.get("page_start"),
            "page_end": metadata.get("page_end"),
            "heading_path": metadata.get("heading_path"),
            "source_filename": metadata.get("source_filename"),
            "document_id": metadata.get("document_id", "document_0001"),
        }
