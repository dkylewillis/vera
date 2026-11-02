"""Prepare dropped documents and decide how each one is shown to the model.

Each source is converted once into ``attachments_dir/<key>/<name>.vera``.
Small files are placed in the prompt in full. Larger files stay searchable.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
from html.parser import HTMLParser
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from vera_app.cancellation import CancellationToken
from vera_app.citations import CitationRegistry, attachment_token_cap
from vera_app.convert import handle_convert, requested_embedding_model
from vera_app.types import Request, WriteEvent
from vera_doc import VeraDocument
from vera_ingest.formats import pick_parser_for_suffix, source_suffix
from vera_ingest.viewer import figures

_TEXT_SUFFIXES = {"txt", "html", "htm"}
_PIPELINE_PACKAGES = {
    "pymupdf": "vera-ingest-pymupdf",
    "markdown": "vera-ingest",
    "ooxml": "vera-ingest-ooxml",
}


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    cleaned = re.sub(r"[^A-Za-z0-9._ -]+", "_", stem).strip(" .")
    return (cleaned or "attachment")[:80]


def _package_version(dist: str) -> str:
    try:
        return version(dist)
    except PackageNotFoundError:
        return ""


def _pipeline_version(parser: str) -> str:
    provider = parser.split(":", 1)[0]
    return _package_version(_PIPELINE_PACKAGES.get(provider, "vera-ingest"))


# Bump when the cached archive layout changes so older cache entries rebuild.
_CACHE_LAYOUT = "original-1"


def cache_key(source: Path, model: str, parser: str) -> str:
    """Hash of file bytes, embedder, parser, pipeline version, and cache layout."""
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    blob = f"{digest}\n{model}\n{parser}\n{_pipeline_version(parser)}\n{_CACHE_LAYOUT}".encode()
    return hashlib.sha256(blob).hexdigest()[:24]


def read_chunks(vera_path: str) -> list[dict[str, Any]]:
    """Read chunk text and metadata in archive order, without vectors."""
    document = VeraDocument.open(vera_path)
    try:
        chunks: list[dict[str, Any]] = []
        for row in document.iter_chunk_text():
            try:
                metadata = json.loads(row["metadata_json"])
            except json.JSONDecodeError:
                metadata = {}
            if not isinstance(metadata, dict):
                metadata = {}
            chunks.append(
                {
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "metadata": metadata,
                }
            )
        return chunks
    finally:
        document.close()


def list_figures(vera_path: str) -> list[dict[str, Any]]:
    """Figure captions stored in an archive, without image bytes."""
    try:
        document = VeraDocument.open(vera_path)
    except OSError:
        return []
    try:
        return figures(document, include_data=False)
    except Exception:
        return []
    finally:
        document.close()


def summarize_chunks(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    tokens = 0
    pages = 0
    outline: list[str] = []
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        count = metadata.get("token_count")
        if isinstance(count, int) and count > 0:
            tokens += count
        else:
            tokens += max(1, len(str(chunk.get("text") or "")) // 4)
        page_end = metadata.get("page_end") or metadata.get("page_start") or 0
        try:
            pages = max(pages, int(page_end))
        except (TypeError, ValueError):
            pass
        heading = str(metadata.get("heading_path") or "").strip()
        top = heading.split(">")[0].strip()
        if top and top not in outline:
            outline.append(top)
    return {
        "token_estimate": tokens,
        "page_count": pages,
        "chunk_count": len(chunks),
        "outline": outline[:12],
    }


def plan_delivery(attachments: list[dict[str, Any]], cap: int) -> dict[str, str]:
    """Give files full text in drop order until the next one would exceed ``cap``.

    Every file after that point is searchable, even if a later file would have
    fit on its own.
    """
    delivery: dict[str, str] = {}
    used = 0
    blocked = False
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_id = str(attachment.get("id") or "")
        if not attachment_id:
            continue
        try:
            tokens = int(attachment.get("token_estimate") or 0)
        except (TypeError, ValueError):
            tokens = 0
        if blocked or used + tokens > cap:
            delivery[attachment_id] = "searchable"
            blocked = True
            continue
        delivery[attachment_id] = "full"
        used += tokens
    return delivery


def apply_full_ids(
    delivery: dict[str, str],
    full_ids: Any,
) -> dict[str, str]:
    """Downgrade full-text files the caller did not ask to resend."""
    if not isinstance(full_ids, list):
        return delivery
    allowed = {str(item) for item in full_ids}
    return {
        attachment_id: mode if mode != "full" or attachment_id in allowed else "searchable"
        for attachment_id, mode in delivery.items()
    }


def manifest_text(attachments: list[dict[str, Any]], delivery: dict[str, str]) -> str:
    lines = ["Attached files:"]
    for index, attachment in enumerate(attachments, start=1):
        if not isinstance(attachment, dict):
            continue
        attachment_id = str(attachment.get("id") or "")
        mode = delivery.get(attachment_id, "searchable")
        how = "included in full below" if mode == "full" else "searchable with search_attachments"
        outline = attachment.get("outline") or []
        outline_text = ""
        if isinstance(outline, list) and outline:
            outline_text = " Outline: " + "; ".join(str(item) for item in outline[:8]) + "."
        lines.append(
            f"- {attachment.get('name') or attachment_id} "
            f"(id {attachment_id}, {attachment.get('page_count') or 0} pages, "
            f"~{attachment.get('token_estimate') or 0} tokens, item {index}): {how}.{outline_text}"
        )
    return "\n".join(lines) if len(lines) > 1 else ""


def chunk_result(attachment: dict[str, Any], chunk: dict[str, Any]) -> dict[str, Any]:
    """Citation result for one stored chunk of an attached archive."""
    metadata = chunk.get("metadata") or {}
    return {
        "chunk_id": chunk.get("chunk_id"),
        "text": chunk.get("text") or "",
        "file": str(attachment.get("vera_path") or ""),
        "page_start": metadata.get("page_start"),
        "page_end": metadata.get("page_end"),
        "heading_path": metadata.get("heading_path"),
        "source_filename": str(attachment.get("name") or "attachment"),
        "document_id": metadata.get("document_id") or "document_0001",
    }


def register_attachments(
    request: Request,
    registry: CitationRegistry,
    chunk_cache: dict[str, list[dict[str, Any]]] | None = None,
) -> None:
    """Give every attached archive its fixed ``[A#]`` range in ``registry``.

    ``label_start`` comes from the composer. Sessions saved before it existed
    number files back to back in attach order.
    """
    cache = chunk_cache if chunk_cache is not None else {}
    next_start = 1
    for row in attachment_rows(request):
        path = str(row.get("vera_path") or "")
        try:
            start = int(row.get("label_start") or 0)
        except (TypeError, ValueError):
            start = 0
        if start < 1:
            start = next_start
        try:
            count = int(row.get("chunk_count") or 0)
        except (TypeError, ValueError):
            count = 0
        next_start = max(next_start, start + max(count, 1))

        def load(row: dict[str, Any] = row, path: str = path) -> list[dict[str, Any]]:
            if path not in cache:
                cache[path] = read_chunks(path)
            return [chunk_result(row, chunk) for chunk in cache[path]]

        registry.add_attachment(path, start, load)


def _without_overlap(previous: str, current: str, max_words: int = 1000) -> str:
    """Drop the words ``current`` repeats from the end of ``previous``."""
    prev_words = previous.split()
    matches = list(re.finditer(r"\S+", current))
    limit = min(len(prev_words), len(matches) - 1, max_words)
    if limit < 1:
        return current
    words = [match.group(0) for match in matches[:limit]]
    for size in range(limit, 0, -1):
        if prev_words[-size] != words[0]:
            continue
        if prev_words[-size:] == words[:size]:
            return current[matches[size - 1].end() :].lstrip()
    return current


def full_text_block(
    attachment: dict[str, Any],
    chunks: list[dict[str, Any]],
    registry: CitationRegistry,
    figure_rows: list[dict[str, Any]] | None = None,
) -> str:
    """Prompt text for one file, in order, with the sliding-window overlap removed.

    Chunk labels are assigned but not yet cited.
    """
    name = str(attachment.get("name") or "attachment")
    attachment_id = str(attachment.get("id") or "")
    lines = [f'<attached_file id="{attachment_id}" name="{name}">']
    previous = ""
    for chunk in chunks:
        metadata = chunk.get("metadata") or {}
        result = chunk_result(attachment, chunk)
        citation_id = registry.label(result, record=False)
        text = str(chunk.get("text") or "")
        shown = _without_overlap(previous, text) if previous else text
        previous = text
        page = metadata.get("page_start") or metadata.get("page_end") or "-"
        heading = str(metadata.get("heading_path") or "").strip()
        location = f"p. {page}" + (f", {heading}" if heading else "")
        lines.append(f"[{citation_id}] ({location}) {shown}")
    for index, figure in enumerate(figure_rows or [], start=1):
        caption = figure.get("caption") or "no caption"
        page = figure.get("page_number") or "-"
        asset_id = figure.get("asset_id") or ""
        lines.append(f"[F{index}] asset_id={asset_id} (p. {page}) {caption}")
    lines.append("</attached_file>")
    return "\n".join(lines)


def _markdown_source(source: Path) -> Path | None:
    """Return a temporary Markdown copy for suffixes the pipelines do not ingest."""
    suffix = source_suffix(source)
    if suffix not in _TEXT_SUFFIXES:
        return None
    text = source.read_text(encoding="utf-8", errors="replace")
    if suffix in {"html", "htm"}:
        parser = _HTMLText()
        parser.feed(text)
        text = "\n\n".join(parser.parts)
    temp = Path(tempfile.mkdtemp(prefix="vera-attach-")) / f"{_safe_stem(source.name)}.md"
    temp.write_text(text, encoding="utf-8")
    return temp


def _validated_archive(path: Path) -> bool:
    if not path.is_file():
        return False
    document = VeraDocument.open(path)
    try:
        report = document.validate()
    finally:
        document.close()
    return bool(report.get("ok"))


def handle_chat_attachment_prepare(
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Convert ``input`` once and return a summary the composer can store."""
    source = Path(str(request.get("input") or "")).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"Attachment was not found: {source}")
    if source_suffix(source) == "vera":
        if not _validated_archive(source):
            raise ValueError(f"{source.name} is not a valid VERA archive.")
        summary = summarize_chunks(read_chunks(str(source)))
        return {"vera_path": str(source), "name": source.name, **summary}

    root = Path(str(request.get("attachments_dir") or "")).expanduser()
    if not str(root):
        raise ValueError("attachments_dir is required")
    root.mkdir(parents=True, exist_ok=True)
    model = requested_embedding_model(request)
    wrapped = _markdown_source(source)
    convert_input = wrapped or source
    try:
        parser = requested_parser_for(convert_input, request)
        key = cache_key(source, model, parser)
        target = root / key / f"{_safe_stem(source.name)}.vera"
        if not _validated_archive(target):
            target.parent.mkdir(parents=True, exist_ok=True)
            handle_convert(
                {
                    "input": str(convert_input),
                    "output": str(target),
                    "model": model,
                    "parser": parser,
                    "store_original": True,
                },
                write_event=write_event,
                cancel=cancel,
            )
        summary = summarize_chunks(read_chunks(str(target)))
        return {"vera_path": str(target), "name": source.name, **summary}
    finally:
        if wrapped is not None:
            shutil.rmtree(wrapped.parent, ignore_errors=True)


def requested_parser_for(source: Path, request: Request) -> str:
    explicit = request.get("parser")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    return pick_parser_for_suffix(source_suffix(source))


SEARCH_ATTACHMENTS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_attachments",
        "description": (
            "Search documents the user attached to this chat. Use it for files "
            "marked searchable. Returns passages with citation ids."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "mode": {"type": "string", "enum": ["hybrid", "semantic", "keyword"]},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
                "ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional attachment ids to limit the search.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}

VIEW_FIGURE_TOOL = {
    "type": "function",
    "function": {
        "name": "view_figure",
        "description": (
            "Show one image to yourself. Pass asset_id from an [F#] line, or the id "
            "of an image the user attached."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "VERA archive path for a document figure."},
                "asset_id": {"type": "string", "description": "Figure asset id or attached image id."},
            },
            "required": ["asset_id"],
            "additionalProperties": False,
        },
    },
}


def attachment_rows(request: Request) -> list[dict[str, Any]]:
    raw = request.get("file_attachments")
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict) and row.get("vera_path")]


def delivery_for(request: Request) -> dict[str, str]:
    rows = attachment_rows(request)
    delivery = plan_delivery(rows, attachment_token_cap(request))
    return apply_full_ids(delivery, request.get("full_attachment_ids"))


def searchable_paths(request: Request, delivery: dict[str, str], ids: list[str] | None = None) -> list[str]:
    wanted = set(ids or [])
    paths: list[str] = []
    for row in attachment_rows(request):
        attachment_id = str(row.get("id") or "")
        if delivery.get(attachment_id) != "searchable":
            continue
        if wanted and attachment_id not in wanted:
            continue
        path = str(row.get("vera_path") or "")
        if path:
            paths.append(path)
    return paths


def build_attachment_prompt(
    request: Request,
    registry: CitationRegistry,
) -> tuple[str, dict[str, str]]:
    """Return prompt text for attachments and the delivery chosen for each."""
    rows = attachment_rows(request)
    if not rows:
        return "", {}
    delivery = delivery_for(request)
    chunk_cache: dict[str, list[dict[str, Any]]] = {}
    register_attachments(request, registry, chunk_cache)
    blocks: list[str] = []
    manifest = manifest_text(rows, delivery)
    if manifest:
        blocks.append(manifest)
    for row in rows:
        attachment_id = str(row.get("id") or "")
        if delivery.get(attachment_id) != "full":
            continue
        path = str(row.get("vera_path") or "")
        if path not in chunk_cache:
            chunk_cache[path] = read_chunks(path)
        chunks = chunk_cache[path]
        figure_rows = list_figures(path)
        blocks.append(full_text_block(row, chunks, registry, figure_rows))
    return "\n\n".join(blocks), delivery


def attachment_usage(
    rows: list[dict[str, Any]],
    delivery: dict[str, str],
    searches: list[dict[str, Any]],
    citations: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    usage = {
        str(row.get("id") or ""): {
            "delivery": delivery.get(str(row.get("id") or ""), "searchable"),
            "searches": 0,
            "cited": 0,
        }
        for row in rows
        if row.get("id")
    }
    attachment_searches = sum(1 for item in searches if item.get("scope") == "attachments")
    by_path = {str(row.get("vera_path") or ""): str(row.get("id") or "") for row in rows}
    for row in rows:
        attachment_id = str(row.get("id") or "")
        if delivery.get(attachment_id) == "searchable" and attachment_searches:
            usage[attachment_id]["searches"] = attachment_searches
    for citation in citations:
        result = citation.get("result") or {}
        attachment_id = by_path.get(str(result.get("file") or ""))
        if attachment_id and attachment_id in usage:
            usage[attachment_id]["cited"] += 1
    return usage
