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

Bridge (Desktop) mode fails closed without ``VERA_BRIDGE_POLICY_PATH``:

    vera-mcp-bridge
    # or: python -m vera_app.sidecar mcp-bridge
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Literal

from vera_doc.corpus import VeraCorpus
from vera_doc.document import VeraDocument
from vera_ingest.viewer import (
    figures,
    format_search_context,
    get_chunk_json,
    get_chunk_regions,
    get_page,
    result_payload,
)

from .access_policy import AccessDenied, AccessPolicy, load_policy_from_env


_AUTO_INSTALL_SEMANTIC_DEPS = "VERA_AUTO_INSTALL_SEMANTIC_DEPS"
_SENTENCE_TRANSFORMERS_REQUIREMENT = "sentence-transformers>=2.7"


def ensure_semantic_dependencies(mode: str) -> None:
    """Install Sentence Transformers before a plugin semantic search request."""
    if mode == "keyword" or os.environ.get(_AUTO_INSTALL_SEMANTIC_DEPS) != "1":
        return
    try:
        importlib.import_module("sentence_transformers")
        return
    except Exception:
        pass

    print(
        "VERA is installing Sentence Transformers for semantic search...",
        file=sys.stderr,
        flush=True,
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pip", "install", _SENTENCE_TRANSFORMERS_REQUIREMENT],
            check=False,
        )
    except OSError as exc:
        raise RuntimeError(
            "VERA could not start pip to install Sentence Transformers for semantic search."
        ) from exc
    if completed.returncode:
        raise RuntimeError(
            "VERA could not install Sentence Transformers for semantic search. "
            "Install `vera-doc[ml]` in the MCP server environment and restart the task."
        )
    importlib.invalidate_caches()
    try:
        importlib.import_module("sentence_transformers")
    except Exception as exc:
        raise RuntimeError(
            "Sentence Transformers is still unavailable after VERA installed it. "
            "Install `vera-doc[ml]` in the MCP server environment and restart the task."
        ) from exc


def _archive_locator(file: str, document: VeraDocument) -> dict[str, str]:
    return {"file": file, "path": str(Path(document.path).resolve())}


def _compact_hit(hit: dict[str, Any], file: str) -> dict[str, Any]:
    """Keep evidence and stable viewer locators, including requested context."""
    result = {
        key: hit[key]
        for key in ("chunk_id", "text", "source_filename", "page_start", "page_end", "heading_path")
        if key in hit
    }
    result["file"] = str(Path(file).resolve())
    for key in ("before_chunks", "after_chunks"):
        if hit.get(key):
            result[key] = [_compact_hit(item, file) for item in hit[key]]
    return result


def _check_output(output: str, pretty: bool, figures: bool, regions: bool) -> None:
    if output == "compact" and (pretty or figures or regions):
        raise ValueError('Use output="full" with pretty, include_figures, or include_regions.')


def build_server(policy: AccessPolicy | None = None):
    """Create the FastMCP server with VERA tools registered.

    When ``policy`` is set, only bridge-safe tools are registered and every archive
    or library path is checked before open. Ordinary local MCP keeps ``policy=None``.
    """
    try:
        from mcp.server.fastmcp import FastMCP, Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "The MCP server requires the vera-mcp package and its 'mcp' dependency"
        ) from exc

    bridge = policy is not None
    instructions = (
        "Search VERA (Vector-Embedded Retrieval Archive) files. An .vera file is a "
        "portable SQLite vector database holding ready-made chunks, embeddings, a "
        "keyword index, metadata, and optional attachments. Use vera_search to retrieve "
        "citation-ready context. Results include source/page/heading metadata when the "
        "extractor supplied it."
    )
    if bridge:
        instructions = (
            "Search the approved local VERA library exposed by Desktop. Call "
            "vera_library_info first for the approved library_root. Use absolute .vera "
            "paths returned by search tools. Retrieval is read-only; conversion and "
            "export are unavailable."
        )

    server = FastMCP("vera", instructions=instructions)

    def _open(file: str) -> VeraDocument:
        if policy is not None:
            path = policy.check_archive(file)
            return VeraDocument.open(path)
        return VeraDocument.open(file)

    def _maybe_tool(name: str) -> bool:
        return policy is None or name in policy.allowed_tools

    if _maybe_tool("vera_library_info"):

        @server.tool()
        def vera_library_info() -> dict[str, Any]:
            """Return the approved library root and supported search capabilities."""
            if policy is None:
                return {
                    "library_root": None,
                    "supported_modes": ["hybrid", "semantic", "keyword"],
                    "unrestricted": True,
                    "message": "Local MCP has no library grant; pass absolute archive paths.",
                }
            return policy.discovery()

    if _maybe_tool("vera_search"):

        @server.tool()
        def vera_search(
            file: str,
            query: str,
            mode: str = "hybrid",
            top_k: int = 10,
            include_figures: bool = False,
            include_regions: bool = False,
            context_chunks: int = 0,
            where: dict[str, str | list[str]] | None = None,
            pretty: bool = False,
            output: Literal["compact", "full"] = "full",
        ) -> dict[str, Any]:
            """Search a VERA file and return citation-ready chunks.

            Set pretty to add the same results as readable Markdown-like context.
            Prefer output="compact" for answers: retains text, citations, archive paths,
            chunk IDs and requested neighbors. Full output supports pretty/figures/regions.
            """
            _check_output(output, pretty, include_figures, include_regions)
            if policy is not None:
                top_k = policy.clamp_top_k(top_k)
                context_chunks = policy.clamp_context_chunks(context_chunks)
            if not bridge:
                ensure_semantic_dependencies(mode)
            doc = _open(file)
            try:
                results = []
                for result in doc.search(
                    text=query,
                    mode=mode,
                    top_k=top_k,
                    context_chunks=context_chunks,
                    where=where,
                ):
                    results.append(
                        result_payload(
                            result,
                            document=doc,
                            include_figures=include_figures,
                            include_regions=include_regions,
                        )
                    )
                response = {"query": query, "mode": mode, "results": results}
                if output == "compact":
                    return {"results": [_compact_hit(hit, str(doc.path)) for hit in results]}
                if pretty:
                    response["context"] = format_search_context(results)
                return response
            finally:
                doc.close()

    if _maybe_tool("vera_corpus_search"):

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
            includes: list[str] | None = None,
            where: dict[str, str | list[str]] | None = None,
            pretty: bool = False,
            output: Literal["compact", "full"] = "full",
        ) -> dict[str, Any]:
            """Search a VERA library, automatically using its fresh local index when available.

            Set pretty to add the same results as readable Markdown-like context.
            Prefer output="compact" for answers: retains evidence, viewer locators,
            requested neighbors and nonempty coverage warnings. Full is the legacy format.
            """
            _check_output(output, pretty, include_figures, include_regions)
            if policy is not None:
                directory = str(policy.check_library_root(directory))
                top_k = policy.clamp_top_k(top_k)
                context_chunks = policy.clamp_context_chunks(context_chunks)
            if not bridge:
                ensure_semantic_dependencies(mode)
            corpus = VeraCorpus.open(
                directory, recursive=recursive, excludes=excludes, includes=includes
            )
            try:
                if policy is not None:
                    allowed_paths: list[str] = []
                    for path in list(corpus.paths):
                        try:
                            allowed_paths.append(str(policy.check_archive(path)))
                        except AccessDenied:
                            # Drop stale or escaped index/discovery members before search.
                            corpus.invalid_files.append(
                                {
                                    "file": "(omitted)",
                                    "category": "denied",
                                    "reason": "Access denied by VERA bridge policy.",
                                }
                            )
                    corpus.paths = allowed_paths
                results = []
                for result in corpus.search(
                    text=query,
                    mode=mode,
                    top_k=top_k,
                    context_chunks=context_chunks,
                    where=where,
                ):
                    if policy is not None:
                        policy.check_archive(result.file)
                    results.append(
                        result_payload(
                            result,
                            document=corpus.document(result.file),
                            include_figures=include_figures,
                            include_regions=include_regions,
                        )
                    )
                response = {
                    "directory": directory,
                    "query": query,
                    "mode": mode,
                    "index": corpus.index_search_report(),
                    "skipped_files": corpus.invalid_files,
                    "skipped_semantic_model_groups": corpus.skipped_semantic_model_groups,
                    "results": results,
                }
                if output == "compact":
                    compact = {"results": [_compact_hit(hit, hit["file"]) for hit in results]}
                    warnings = {
                        key: response[key]
                        for key in ("skipped_files", "skipped_semantic_model_groups")
                        if response[key]
                    }
                    if warnings:
                        compact["warnings"] = warnings
                    return compact
                if pretty:
                    response["context"] = format_search_context(results)
                return response
            finally:
                corpus.close()

    if _maybe_tool("vera_inspect"):

        @server.tool()
        def vera_inspect(file: str) -> dict[str, Any]:
            """Get metadata for a VERA file."""
            doc = _open(file)
            try:
                return {**doc.inspect(), **_archive_locator(file, doc)}
            finally:
                doc.close()

    if policy is None:

        @server.tool()
        def vera_validate(file: str) -> dict[str, Any]:
            """Validate a VERA file."""
            doc = _open(file)
            try:
                return {**doc.validate(), **_archive_locator(file, doc)}
            finally:
                doc.close()

    if _maybe_tool("vera_figures"):

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

    if _maybe_tool("vera_get_figure"):

        @server.tool(structured_output=False)
        def vera_get_figure(file: str, asset_id: str):
            """Return one stored figure as image content plus citation metadata.

            Image bytes are MCP Image content. Metadata (caption, page, bbox, mime
            type) is JSON text. A missing or non-figure asset id returns an error
            object rather than attachment bytes.
            """
            doc = _open(file)
            try:
                items = figures(doc, include_data=True, attachment_ids=[asset_id])
                if not items:
                    return {"error": f"Figure {asset_id} not found"}
                figure = items[0]
                data = figure.pop("data")
                mime = str(figure.get("mime_type") or "image/png")
                fmt = mime.split("/", 1)[-1] if "/" in mime else mime
                if fmt == "jpg":
                    fmt = "jpeg"
                return [figure, Image(data=data, format=fmt)]
            finally:
                doc.close()

    if _maybe_tool("vera_get_page"):

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

    if _maybe_tool("vera_get_chunk"):

        @server.tool()
        def vera_get_chunk(
            file: str,
            chunk_id: str,
            include_figures: bool = False,
            include_regions: bool = False,
        ) -> dict[str, Any]:
            """Fetch one stored chunk by id as citation-ready JSON."""
            if not str(chunk_id).strip():
                return {"ok": False, "error": f"chunk not found: {chunk_id}"}
            doc = _open(file)
            try:
                try:
                    records = doc.get(ids=[chunk_id])
                    if not records:
                        return {"ok": False, "error": f"chunk not found: {chunk_id}"}
                    return get_chunk_json(
                        file,
                        doc,
                        records[0],
                        include_figures=include_figures,
                        include_regions=include_regions,
                    )
                except ValueError as exc:
                    return {"ok": False, "error": str(exc)}
            finally:
                doc.close()

    if _maybe_tool("vera_get_chunk_regions"):

        @server.tool()
        def vera_get_chunk_regions(file: str, chunk_id: str) -> list[dict[str, Any]]:
            """Get visual grounding regions for a chunk."""
            doc = _open(file)
            try:
                return get_chunk_regions(doc, chunk_id)
            finally:
                doc.close()

    from .source_viewer import register_source_viewer

    if policy is None or "vera_show_sources" in policy.allowed_tools:
        register_source_viewer(server, policy=policy)
    return server


def main() -> int:
    """Entry point for ``vera mcp``: unrestricted local server over stdio."""
    build_server().run()
    return 0


def main_bridge() -> int:
    """Fail-closed bridge entry: requires ``VERA_BRIDGE_POLICY_PATH``."""
    # Packaged bridge must never auto-install semantic deps over the network.
    os.environ.pop(_AUTO_INSTALL_SEMANTIC_DEPS, None)
    try:
        policy = load_policy_from_env()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    build_server(policy=policy).run()
    return 0
