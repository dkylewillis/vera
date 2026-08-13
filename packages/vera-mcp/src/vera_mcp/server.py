"""MCP (Model Context Protocol) server exposing VERA files to AI agents.

Run with:

    vera mcp

or configure in an MCP client (e.g. VS Code .vscode/mcp.json):

    {
      "servers": {
        "vera": {"command": "uv", "args": ["run", "--extra", "mcp", "vera", "mcp"]}
      }
    }

Install the integration package with: pip install vera-mcp
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vera_doc.corpus import VeraCorpus
from vera_doc.document import VeraDocument
from vera_ingest.viewer import (
    figures,
    get_chunk_regions,
    get_page,
    result_payload,
)


def _open(file: str) -> VeraDocument:
    return VeraDocument.open(file)


def _archive_locator(file: str, document: VeraDocument) -> dict[str, str]:
    return {"file": file, "path": str(Path(document.path).resolve())}


def build_server():
    """Create the FastMCP server with VERA tools registered."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The MCP server requires the vera-mcp package and its 'mcp' dependency"
        ) from exc

    server = FastMCP(
        "vera",
        instructions=(
            "Search VERA (Vector-Embedded Retrieval Archive) files. An .vera file is a "
            "portable SQLite vector database holding ready-made chunks, embeddings, a "
            "keyword index, metadata, and optional attachments. Use vera_search to retrieve "
            "citation-ready context. Results include source/page/heading metadata when the "
            "extractor supplied it."
        ),
    )

    @server.tool()
    def vera_search(
        file: str,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        include_figures: bool = False,
        include_regions: bool = False,
        context_chunks: int = 0,
    ) -> dict[str, Any]:
        """Search a VERA file and return citation-ready chunks."""
        doc = _open(file)
        try:
            results = []
            for result in doc.search(
                text=query, mode=mode, top_k=top_k, context_chunks=context_chunks
            ):
                results.append(
                    result_payload(
                        result,
                        document=doc,
                        include_figures=include_figures,
                        include_regions=include_regions,
                    )
                )
            return {"query": query, "mode": mode, "results": results}
        finally:
            doc.close()

    @server.tool()
    def vera_corpus_search(
        directory: str,
        query: str,
        mode: str = "hybrid",
        top_k: int = 10,
        include_figures: bool = False,
        include_regions: bool = False,
        context_chunks: int = 0,
        recursive: bool | None = None,
        excludes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search a VERA library, automatically using its fresh local index when available."""
        corpus = VeraCorpus.open(directory, recursive=recursive, excludes=excludes)
        try:
            results = []
            for result in corpus.search(
                text=query, mode=mode, top_k=top_k, context_chunks=context_chunks
            ):
                results.append(
                    result_payload(
                        result,
                        document=corpus.document(result.file),
                        include_figures=include_figures,
                        include_regions=include_regions,
                    )
                )
            return {
                "directory": directory,
                "query": query,
                "mode": mode,
                "index": {"used": corpus.uses_index, **corpus.index_status},
                "skipped_files": corpus.invalid_files,
                "skipped_semantic_model_groups": corpus.skipped_semantic_model_groups,
                "results": results,
            }
        finally:
            corpus.close()

    @server.tool()
    def vera_inspect(file: str) -> dict[str, Any]:
        """Get metadata for a VERA file."""
        doc = _open(file)
        try:
            return {**doc.inspect(), **_archive_locator(file, doc)}
        finally:
            doc.close()

    @server.tool()
    def vera_validate(file: str) -> dict[str, Any]:
        """Validate a VERA file."""
        doc = _open(file)
        try:
            return {**doc.validate(), **_archive_locator(file, doc)}
        finally:
            doc.close()

    @server.tool()
    def vera_figures(
        file: str,
        page_start: int | None = None,
        page_end: int | None = None,
    ) -> list[dict[str, Any]]:
        """List figures in a VERA file with captions and page locations."""
        doc = _open(file)
        try:
            return figures(doc, page_start=page_start, page_end=page_end)
        finally:
            doc.close()

    @server.tool()
    def vera_get_page(file: str, page_number: int) -> dict[str, Any]:
        """Get the full text of a single page."""
        doc = _open(file)
        try:
            page = get_page(doc, page_number)
            if page is None:
                return {"error": f"Page {page_number} not found"}
            return page
        finally:
            doc.close()

    @server.tool()
    def vera_get_chunk_regions(file: str, chunk_id: str) -> list[dict[str, Any]]:
        """Get visual grounding regions for a chunk."""
        doc = _open(file)
        try:
            return get_chunk_regions(doc, chunk_id)
        finally:
            doc.close()

    return server


def main() -> int:
    """Entry point for `vera mcp`: run the server over stdio."""
    build_server().run()
    return 0
