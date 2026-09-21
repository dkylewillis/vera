"""Source views for MCP Apps; storage and ingest remain UI-independent."""

from __future__ import annotations

import base64
import math
import sqlite3
from importlib.resources import files
from pathlib import Path
from typing import Annotated, Any

from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field

from vera_doc import VeraDocument
from vera_ingest.viewer import get_chunk_json, get_source_document

from .access_policy import AccessDenied, AccessPolicy

RESOURCE_URI = "ui://vera/source-viewer-v1.html"
MAX_SOURCE_BYTES = 40 * 1024 * 1024
MAX_IMAGE_BYTES = 3 * 1024 * 1024
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)


class SourceRef(BaseModel):
    file: str = Field(min_length=1, description="Absolute path to a searched .vera archive.")
    chunk_id: str = Field(min_length=1, description="Chunk ID returned by VERA search.")
    id: str | None = Field(
        default=None,
        pattern=r"^C[1-9]\d*$",
        description="Optional citation marker used in the response, for example C1.",
    )


def _resolve_archive(ref: SourceRef, policy: AccessPolicy | None) -> Path:
    path = Path(ref.file)
    if policy is not None:
        return policy.check_archive(path)
    if not path.is_absolute() or path.suffix.lower() != ".vera":
        raise ValueError("Use an absolute path to a .vera archive.")
    return path


def read_chunk(ref: SourceRef, policy: AccessPolicy | None = None) -> dict[str, Any]:
    path = _resolve_archive(ref, policy)
    with VeraDocument.open(path) as doc:
        records = doc.get(ids=[ref.chunk_id])
        if not records:
            raise ValueError(f"Chunk not found: {ref.chunk_id}")
        data = get_chunk_json(str(path), doc, records[0], include_regions=True)
    # Only citation fields from storage are exposed as presentation metadata.
    return {
        key: data[key]
        for key in (
            "file",
            "chunk_id",
            "text",
            "source_filename",
            "page_start",
            "page_end",
            "heading_path",
            "regions",
        )
        if key in data
    }


def _pdf_view(source, regions, requested_page: int, initial_page: int) -> dict[str, Any]:
    try:
        import pymupdf
    except ImportError:
        return {"kind": "text", "notice": 'PDF preview requires pip install "vera-mcp[viewer]".'}
    with pymupdf.open(stream=source.data, filetype="pdf") as pdf:
        number = requested_page or initial_page
        if number < 1 or number > len(pdf):
            raise ValueError(f"Page must be between 1 and {len(pdf)}.")
        page = pdf[number - 1]
        size = page.rect
        scale = min(2.0, 1400 / max(size.width, size.height))
        image = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False).tobytes("png")
        if len(image) > MAX_IMAGE_BYTES:
            raise ValueError("Page preview is too large; use the desktop viewer.")
        boxes = []
        for region in regions:
            if region.get("page_number") != number or page.rotation:
                continue
            bbox = region.get("bbox")
            width, height = region.get("page_width"), region.get("page_height")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue
            if not all(
                isinstance(v, (int, float)) and math.isfinite(v) for v in [*bbox, width, height]
            ):
                continue
            if width <= 0 or height <= 0:
                continue
            # Never project coordinates from a differently sized source page.
            if abs(width - size.width) > 2 or abs(height - size.height) > 2:
                continue
            x0, y0, x1, y1 = bbox
            x0, x1 = max(0, x0 / width), min(1, x1 / width)
            y0, y1 = max(0, y0 / height), min(1, y1 / height)
            if x1 > x0 and y1 > y0:
                boxes.append([x0, y0, x1 - x0, y1 - y0])
        return {
            "kind": "pdf",
            "page": number,
            "page_count": len(pdf),
            "page_width": float(size.width),
            "page_height": float(size.height),
            "image": "data:image/png;base64," + base64.b64encode(image).decode("ascii"),
            "boxes": boxes,
            "notice": ""
            if boxes
            else (
                "Highlights unavailable for rotated source pages."
                if page.rotation
                else "No verified highlight locations on this page."
            ),
        }


def source_view(
    ref: SourceRef, page: int = 0, policy: AccessPolicy | None = None
) -> dict[str, Any]:
    if page < 0:
        raise ValueError("Page must be zero (first cited page) or a positive page number.")
    path = _resolve_archive(ref, policy)
    chunk = read_chunk(ref, policy=policy)
    base = {"file": str(path), "chunk_id": ref.chunk_id, "text": chunk["text"]}
    with VeraDocument.open(path) as doc:
        try:
            source = get_source_document(doc)
        except ValueError as exc:
            return {**base, "kind": "text", "notice": str(exc)}
    if len(source.data) > MAX_SOURCE_BYTES:
        return {**base, "kind": "text", "notice": "Original exceeds the 40 MiB preview limit."}
    regions = chunk.get("regions", [])
    if source.media_type == "application/pdf":
        start = chunk.get("page_start")
        initial = start if isinstance(start, int) and start > 0 else 1
        try:
            return {**base, **_pdf_view(source, regions, page, initial)}
        except (RuntimeError, ValueError) as exc:
            return {**base, "kind": "text", "notice": f"PDF preview unavailable: {exc}"}
    if source.media_type in ("text/markdown", "text/plain") or Path(
        source.filename or ""
    ).suffix.lower() in (".md", ".markdown"):
        text = source.data.decode("utf-8-sig")
        lines = text.splitlines()
        spans = []
        for region in regions:
            start = region.get("start", {}).get("line")
            end = region.get("end", {}).get("line", start)
            if (
                region.get("kind") == "text_span"
                and isinstance(start, int)
                and isinstance(end, int)
                and 1 <= start <= end <= len(lines)
            ):
                spans.append([start, end])
        # Send a bounded window around the first highlighted line, with navigation.
        count = max(1, (len(lines) + 199) // 200)
        selected = page or ((spans[0][0] - 1) // 200 + 1 if spans else 1)
        if not 1 <= selected <= count:
            raise ValueError(f"Text section must be between 1 and {count}.")
        offset = (selected - 1) * 200
        return {
            **base,
            "kind": "markdown",
            "lines": lines[offset : offset + 200],
            "line_start": offset + 1,
            "spans": spans,
            "page": selected,
            "page_count": count,
            "notice": "" if spans else "No stored line highlights.",
        }
    return {
        **base,
        "kind": "text",
        "notice": "This source type has no preview; showing stored passage.",
    }


def _result(summary: dict, view: dict) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text=summary.get("message", "Source viewer ready."))],
        structuredContent=summary,
        _meta={"vera/view": view},
    )


def register_source_viewer(server, policy: AccessPolicy | None = None) -> None:
    max_sources = policy.max_sources if policy is not None else 12

    @server.resource(
        RESOURCE_URI,
        mime_type="text/html;profile=mcp-app",
        name="VERA source viewer",
        meta={"ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}}},
    )
    def viewer_html() -> str:
        return files("vera_mcp").joinpath("ui/source-viewer.html").read_text(encoding="utf-8")

    @server.tool(
        annotations=READ_ONLY,
        meta={
            "ui": {"resourceUri": RESOURCE_URI},
            "openai/outputTemplate": RESOURCE_URI,
            "openai/toolInvocation/invoking": "Opening sources",
            "openai/toolInvocation/invoked": "Sources ready",
        },
    )
    def vera_show_sources(
        sources: Annotated[list[SourceRef], Field(min_length=1, max_length=12)],
    ) -> CallToolResult:
        """Show an Open VERA sources button for retrieved citations. First search
        VERA; pass response citation IDs, returned archive paths, and chunk IDs.
        The viewer opens PDF or Markdown highlights. Does not search or alter archives."""
        if len(sources) > max_sources:
            raise AccessDenied(f"At most {max_sources} sources may be opened at once.")
        cards = []
        for ref in sources:
            try:
                card = read_chunk(ref, policy=policy)
            except AccessDenied:
                card = {
                    "file": "(omitted)",
                    "chunk_id": ref.chunk_id,
                    "error": "Access denied by VERA bridge policy.",
                }
            except (ValueError, OSError, sqlite3.Error) as exc:
                message = str(exc)
                if ":\\" in message or message.startswith("/") or "\\\\" in message:
                    message = "Source could not be opened."
                card = {
                    "file": "(omitted)" if policy else ref.file,
                    "chunk_id": ref.chunk_id,
                    "error": message,
                }
            cards.append({"id": ref.id, **card} if ref.id else card)
        summary = {
            "sources": [{k: v for k, v in c.items() if k != "regions"} for c in cards],
            "message": f"VERA source viewer ready with {len(cards)} references.",
        }
        return _result(
            summary,
            {
                "mode": "launcher",
                "sources": cards,
                "selected": None,
                "view": None,
            },
        )

    @server.tool(
        annotations=READ_ONLY,
        meta={"ui": {"visibility": ["app"]}, "openai/widgetAccessible": True},
    )
    def vera_source_page(file: str, chunk_id: str, page: int = 0) -> CallToolResult:
        """Read one source page for the viewer's scrollable PDF or Markdown view.

        Zero opens the first cited page; positive numbers select a PDF page or a
        200-line Markdown section. The viewer loads further PDF pages on demand.
        """
        try:
            view = source_view(SourceRef(file=file, chunk_id=chunk_id), page, policy=policy)
        except AccessDenied as exc:
            raise AccessDenied("Access denied by VERA bridge policy.") from exc
        return _result(
            {
                "file": view.get("file", file),
                "chunk_id": chunk_id,
                "page": view.get("page"),
                "message": view.get("notice") or "Source page loaded.",
            },
            view,
        )
