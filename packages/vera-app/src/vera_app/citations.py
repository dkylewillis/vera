"""Session-wide citation labels shared by every agent tool.

Labels are keyed by ``file::chunk_id`` so two archives that both start at
``chunk_0001`` do not share a ``[C#]``. Older sessions that stored only
``chunk_id`` still match through a legacy fallback.

Chunks of files attached to the chat use ``[A#]`` instead. Each attachment
owns a fixed range starting at its ``label_start``, so a chunk keeps the same
number on every turn and never collides with library search results.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Any

_CITATION_RE = re.compile(r"\[([CA]\d+)\]")
_ID_RE = re.compile(r"C(\d+)")
_ATTACHMENT_ID_RE = re.compile(r"A(\d+)")

AttachmentLoader = Callable[[], list[dict[str, Any]]]


def _same_file(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))

_LOCAL_PROVIDERS = {"ollama", "lmstudio", "lm_studio", "lm-studio"}


def _llm(request: dict[str, Any]) -> dict[str, Any]:
    raw = request.get("llm")
    return raw if isinstance(raw, dict) else {}


def is_local_provider(request: dict[str, Any]) -> bool:
    """True for Ollama and LM Studio, which default to a small context window."""
    llm = _llm(request)
    provider = str(llm.get("provider") or "").lower().replace(" ", "").replace("_", "")
    base = str(llm.get("base_url") or "").lower()
    if provider in {name.replace("_", "").replace("-", "") for name in _LOCAL_PROVIDERS}:
        return True
    if "ollama" in provider or "lmstudio" in provider:
        return True
    return ":11434" in base or ":1234" in base


def context_token_budget(request: dict[str, Any]) -> int:
    """Context window used to size evidence and attachment budgets.

    An explicit ``context_tokens`` on the provider payload wins. Otherwise
    local providers default to 8k tokens and cloud providers to 128k.
    """
    llm = _llm(request)
    explicit = llm.get("context_tokens")
    if explicit not in (None, ""):
        try:
            return max(256, int(explicit))
        except (TypeError, ValueError):
            pass
    return 8_000 if is_local_provider(request) else 128_000


def evidence_token_budget(request: dict[str, Any]) -> int:
    """Tokens of earlier evidence to resend with a follow-up question."""
    llm = _llm(request)
    if llm.get("context_tokens") in (None, "") and is_local_provider(request):
        return 2_000
    return max(256, min(8_000, int(context_token_budget(request) * 0.10)))


def attachment_token_cap(request: dict[str, Any]) -> int:
    """Tokens of attached-file text that may be placed in the prompt in full."""
    return max(256, min(40_000, int(context_token_budget(request) * 0.40)))


class CitationRegistry:
    """Assigns stable ``[C#]`` ids and records citations for one answer."""

    def __init__(self) -> None:
        self.recorded: list[dict[str, Any]] = []
        self._by_key: dict[str, dict[str, Any]] = {}
        self._by_id: dict[str, dict[str, Any]] = {}
        self._counter = 0
        self.fallback_file = ""
        self._attachments: list[dict[str, Any]] = []

    def add_attachment(self, file: str, start: int, loader: AttachmentLoader) -> None:
        """Reserve ``[A{start}]`` onward for the chunks of one attached archive.

        ``loader`` returns the archive's chunk results in order. It runs only
        when a chunk of that file is labelled or an ``[A#]`` id is looked up.
        """
        if not file or start < 1:
            return
        self._attachments.append({"file": file, "start": start, "loader": loader, "rows": None})

    def _attachment_rows(self, attachment: dict[str, Any]) -> list[dict[str, Any]]:
        if attachment["rows"] is None:
            try:
                attachment["rows"] = list(attachment["loader"]())
            except Exception:
                attachment["rows"] = []
        return attachment["rows"]

    def _attachment_id_for(self, result: dict[str, Any]) -> str | None:
        file = str(result.get("file") or self.fallback_file or "")
        chunk_id = str(result.get("chunk_id") or "")
        if not file or not chunk_id:
            return None
        for attachment in self._attachments:
            if not _same_file(attachment["file"], file):
                continue
            for index, row in enumerate(self._attachment_rows(attachment)):
                if str(row.get("chunk_id") or "") == chunk_id:
                    return f"A{attachment['start'] + index}"
        return None

    def _attachment_entry(self, citation_id: str) -> dict[str, Any] | None:
        match = _ATTACHMENT_ID_RE.fullmatch(citation_id)
        if not match:
            return None
        number = int(match.group(1))
        for attachment in self._attachments:
            index = number - attachment["start"]
            if index < 0:
                continue
            rows = self._attachment_rows(attachment)
            if index >= len(rows):
                continue
            result = dict(rows[index])
            result.setdefault("file", attachment["file"])
            entry = {"id": citation_id, "label": _label(citation_id, result), "result": result}
            self._by_id[citation_id] = entry
            key = self.citation_key(result)
            if key:
                self._by_key.setdefault(key, entry)
            return entry
        return None

    def citation_key(self, result: dict[str, Any]) -> str:
        chunk_id = str(result.get("chunk_id") or "").strip()
        file = str(result.get("file") or self.fallback_file or "").strip()
        if file and chunk_id:
            return f"{file}::{chunk_id}"
        return chunk_id

    def seed_legacy_map(self, mapping: dict[str, str], start: int = 0) -> None:
        """Seed from the ``chunk_id -> citation id`` map SearchTool used to take."""
        self._counter = max(self._counter, start)
        for chunk_id, citation_id in mapping.items():
            if not chunk_id or not citation_id:
                continue
            self._remember(
                str(citation_id),
                str(chunk_id),
                {"chunk_id": str(chunk_id)},
            )

    def seed_request(self, request: dict[str, Any]) -> None:
        """Seed labels from ``prior_citations`` and richer ``prior_evidence``."""
        raw = request.get("prior_citations")
        if isinstance(raw, list):
            for entry in raw:
                if not isinstance(entry, dict):
                    continue
                citation_id = str(entry.get("id") or "").strip()
                chunk_id = str(entry.get("chunk_id") or "").strip()
                if not citation_id or not chunk_id:
                    continue
                file = str(entry.get("file") or "").strip()
                result = {"chunk_id": chunk_id}
                if file:
                    result["file"] = file
                key = f"{file}::{chunk_id}" if file else chunk_id
                self._remember(citation_id, key, result)
                if file:
                    self._by_key.setdefault(chunk_id, self._by_id[citation_id])
        evidence = request.get("prior_evidence")
        if isinstance(evidence, list):
            for entry in evidence:
                if not isinstance(entry, dict):
                    continue
                citation_id = str(entry.get("id") or "").strip()
                chunk_id = str(entry.get("chunk_id") or "").strip()
                if not citation_id or not chunk_id:
                    continue
                file = str(entry.get("file") or "").strip()
                result = {
                    "chunk_id": chunk_id,
                    "text": str(entry.get("text") or ""),
                    "page_start": entry.get("page_start"),
                    "page_end": entry.get("page_end"),
                    "heading_path": entry.get("heading_path"),
                    "source_filename": entry.get("source_filename"),
                }
                if file:
                    result["file"] = file
                key = f"{file}::{chunk_id}" if file else chunk_id
                self._remember(citation_id, key, result, prefer_result=True)

    def label(self, result: dict[str, Any], *, record: bool = True) -> str:
        """Return the citation id for ``result``, recording it when asked.

        ``record=False`` labels prompt text (full-text attachments) without
        putting the chunk in the citation list until the answer cites it.
        """
        chunk_id = str(result.get("chunk_id") or "").strip()
        key = self.citation_key(result)
        if not key:
            key = f"chunk_{len(self._by_key)}"
            chunk_id = chunk_id or key
        existing = self._by_key.get(key)
        if existing is None and chunk_id:
            legacy = self._by_key.get(chunk_id)
            if legacy is not None and not str((legacy.get("result") or {}).get("file") or ""):
                existing = legacy
                if key != chunk_id:
                    self._by_key[key] = legacy
        if existing is not None:
            if record:
                merged = dict(existing.get("result") or {})
                merged.update({k: v for k, v in result.items() if v is not None})
                existing["result"] = merged
                existing["label"] = _label(str(existing["id"]), merged)
                if existing not in self.recorded:
                    self.recorded.append(existing)
            return str(existing["id"])
        citation_id = self._attachment_id_for(result)
        if citation_id is None:
            self._counter += 1
            citation_id = f"C{self._counter}"
        entry = {
            "id": citation_id,
            "label": _label(citation_id, result),
            "result": result,
        }
        self._by_key[key] = entry
        self._by_id[citation_id] = entry
        if record:
            self.recorded.append(entry)
        return citation_id

    def lookup(self, citation_id: str) -> dict[str, Any] | None:
        return self._by_id.get(citation_id) or self._attachment_entry(citation_id)

    def cite(self, citation_id: str) -> bool:
        """Record a previously labelled chunk because the answer cited it."""
        entry = self.lookup(citation_id)
        if entry is None:
            return False
        if entry not in self.recorded:
            self.recorded.append(entry)
        return True

    def resolve_answer(self, text: str) -> list[str]:
        """Add cited-but-not-retrieved labels to ``recorded``. Return unknown ids."""
        unresolved: list[str] = []
        seen: set[str] = set()
        for match in _CITATION_RE.finditer(text or ""):
            citation_id = match.group(1)
            if citation_id in seen:
                continue
            seen.add(citation_id)
            if not self.cite(citation_id):
                unresolved.append(citation_id)
        return unresolved

    def seen(self, result: dict[str, Any]) -> bool:
        """True when this answer already recorded the chunk."""
        key = self.citation_key(result) or str(result.get("chunk_id") or "")
        if not key:
            return False
        entry = self._by_key.get(key)
        return entry is not None and entry in self.recorded

    def _remember(
        self,
        citation_id: str,
        key: str,
        result: dict[str, Any],
        *,
        prefer_result: bool = False,
    ) -> None:
        entry = self._by_id.get(citation_id)
        if entry is None:
            entry = {
                "id": citation_id,
                "label": _label(citation_id, result),
                "result": dict(result),
            }
            self._by_id[citation_id] = entry
        elif prefer_result:
            merged = dict(entry.get("result") or {})
            for field, value in result.items():
                if value not in (None, ""):
                    merged[field] = value
            entry["result"] = merged
            entry["label"] = _label(citation_id, merged)
        self._by_key.setdefault(key, entry)
        match = _ID_RE.fullmatch(citation_id)
        if match:
            self._counter = max(self._counter, int(match.group(1)))


def _label(citation_id: str, result: dict[str, Any]) -> str:
    page = result.get("page_start") or result.get("page_end") or "-"
    return f"[{citation_id}] p. {page}"


def evidence_block(entries: Any, budget_tokens: int) -> str:
    """Render earlier citations for the prompt, newest and latest-turn first.

    ``entries`` is the ``prior_evidence`` list. Items with ``from_latest`` are
    kept ahead of older turns. The block stops once ``budget_tokens`` is used.
    """
    if not isinstance(entries, list) or budget_tokens <= 0:
        return ""
    dicts = [entry for entry in entries if isinstance(entry, dict)]
    ordered = [entry for entry in dicts if entry.get("from_latest")] + [
        entry for entry in dicts if not entry.get("from_latest")
    ]
    header = (
        "Evidence retrieved earlier in this conversation. "
        "Reuse these citation ids when they support your answer."
    )
    used = max(1, len(header) // 4)
    lines: list[str] = []
    for entry in ordered:
        text = " ".join(str(entry.get("text") or "").split())
        citation_id = str(entry.get("id") or "").strip()
        if not text or not citation_id:
            continue
        file_name = entry.get("source_filename") or entry.get("file") or "document"
        page = entry.get("page_start") or entry.get("page_end") or "-"
        heading = str(entry.get("heading_path") or "").strip()
        location = f"{file_name}, p. {page}"
        if heading:
            location = f"{location}, {heading}"
        line = f"[{citation_id}] ({location}) {text}"
        cost = max(1, len(line) // 4)
        if lines and used + cost > budget_tokens:
            break
        lines.append(line)
        used += cost
    if not lines:
        return ""
    return header + "\n" + "\n".join(lines)
