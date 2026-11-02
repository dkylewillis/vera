"""Render a grounded Markdown report and write it under the drafts folder."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from vera_app.citations import CitationRegistry

_CITATION_RE = re.compile(r"\[([CA]\d+)\]")
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


def _yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_report(title: str, content: str, registry: CitationRegistry) -> tuple[str, list[str]]:
    """Turn ``[C#]`` and ``[A#]`` markers into footnotes. Unknown ids are removed and returned."""
    footnotes: list[str] = []
    mapping: dict[str, int] = {}
    missing: list[str] = []
    sources: list[str] = []

    def replace(match: re.Match[str]) -> str:
        citation_id = match.group(1)
        entry = registry.lookup(citation_id)
        if entry is None:
            if citation_id not in missing:
                missing.append(citation_id)
            return ""
        number = mapping.get(citation_id)
        if number is None:
            number = len(mapping) + 1
            mapping[citation_id] = number
            result = entry.get("result") or {}
            file_name = str(result.get("source_filename") or result.get("file") or "source")
            page = result.get("page_start") or result.get("page_end") or "-"
            heading = str(result.get("heading_path") or "").strip()
            location = f"{file_name}, p. {page}"
            if heading:
                location = f"{location}, {heading}"
            footnotes.append(f"[^{number}]: {location}")
            if file_name not in sources:
                sources.append(file_name)
        return f"[^{number}]"

    body = _CITATION_RE.sub(replace, content or "").strip()
    source_lines = "\n".join(f"  - {_yaml_quote(item)}" for item in sources) or "  []"
    front = (
        "---\n"
        f"title: {_yaml_quote(title or 'Report')}\n"
        f"created: {date.today().isoformat()}\n"
        f"sources:\n{source_lines}\n"
        "---\n\n"
    )
    notes = "\n".join(footnotes)
    text = front + body + ("\n\n" + notes if notes else "") + "\n"
    return text, missing


def safe_markdown_name(filename: str) -> str:
    """Basename only, forced to ``.md``, with unsafe characters removed."""
    base = Path(filename or "report.md").name
    stem = Path(base).stem
    cleaned = _UNSAFE.sub("_", stem).strip(" ._") or "report"
    return f"{cleaned[:80]}.md"


def write_draft(drafts_dir: str, session_id: str, filename: str, text: str) -> dict[str, Any]:
    """Write ``text`` inside ``drafts_dir/<session>/``, versioning when the name exists."""
    root = Path(drafts_dir).expanduser().resolve()
    session = _UNSAFE.sub("_", Path(session_id or "session").name).strip(" ._") or "session"
    folder = (root / session).resolve()
    if root != folder and root not in folder.parents:
        raise ValueError("Draft path escaped the drafts folder.")
    folder.mkdir(parents=True, exist_ok=True)
    name = safe_markdown_name(filename)
    target = (folder / name).resolve()
    version = 1
    if target.exists():
        stem = Path(name).stem
        version = 2
        while True:
            candidate = (folder / f"{stem}.v{version}.md").resolve()
            if root not in candidate.parents:
                raise ValueError("Draft path escaped the drafts folder.")
            if not candidate.exists():
                target = candidate
                break
            version += 1
    if root not in target.parents:
        raise ValueError("Draft path escaped the drafts folder.")
    target.write_text(text, encoding="utf-8")
    return {"path": str(target), "filename": target.name, "version": version}


def read_draft(drafts_dir: str, path: str, limit: int = 50_000) -> str:
    """Read a draft only when it lives under ``drafts_dir``."""
    root = Path(drafts_dir).expanduser().resolve()
    target = Path(path).expanduser().resolve()
    if root != target and root not in target.parents:
        return ""
    if not target.is_file():
        return ""
    return target.read_text(encoding="utf-8")[:limit]


def handle_render_markdown(request: dict[str, Any]) -> dict[str, Any]:
    """Render an existing answer as a Markdown file for Save as Markdown."""
    registry = CitationRegistry()
    raw = request.get("citations")
    evidence: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            result = item.get("result") if isinstance(item.get("result"), dict) else item
            chunk_id = str(result.get("chunk_id") or "").strip()
            citation_id = str(item.get("id") or "").strip()
            if not citation_id or not chunk_id:
                continue
            evidence.append(
                {
                    "id": citation_id,
                    "chunk_id": chunk_id,
                    "file": result.get("file"),
                    "text": result.get("text"),
                    "page_start": result.get("page_start"),
                    "page_end": result.get("page_end"),
                    "heading_path": result.get("heading_path"),
                    "source_filename": result.get("source_filename"),
                }
            )
        registry.seed_request({"prior_evidence": evidence})
    text, _missing = render_report(
        str(request.get("title") or "Answer"),
        str(request.get("content") or ""),
        registry,
    )
    drafts_dir = str(request.get("drafts_dir") or "")
    if not drafts_dir:
        raise ValueError("drafts_dir is required")
    saved = write_draft(
        drafts_dir,
        str(request.get("session_id") or "session"),
        str(request.get("filename") or "answer.md"),
        text,
    )
    saved["title"] = str(request.get("title") or "Answer")
    return saved


def current_draft_block(request: dict[str, Any]) -> str:
    """Latest draft text, included so a follow-up can revise it."""
    drafts_dir = str(request.get("drafts_dir") or "")
    raw = request.get("current_drafts")
    if not drafts_dir or not isinstance(raw, list):
        return ""
    parts: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = read_draft(drafts_dir, str(item.get("path") or ""))
        if not text:
            continue
        name = item.get("filename") or Path(str(item.get("path") or "")).name
        parts.append(
            f"Current draft ({name}). Citation footnotes refer to sources already used. "
            f"Revise it by calling write_markdown again.\n\n{text}"
        )
    return "\n\n".join(parts)
