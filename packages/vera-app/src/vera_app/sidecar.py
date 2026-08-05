from __future__ import annotations

import base64
import copy
import hashlib
import json
import re
import sys
import tempfile
import threading
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vera import (
    AttachmentRecord,
    VeraDocument,
    build_library_index,
    library_index_status,
    update_library_index,
)
from vera.corpus import VeraCorpus
from vera_ingest import batch_convert, convert
from vera_ingest.viewer import (
    export_source_document,
    figures,
    figures_for,
    get_page,
    get_source_document,
    regions_for,
)
from vera_app.cancellation import CancellationToken, CancelledError, SkipCurrentError
from vera_app.llm import (
    ChatResponse,
    LlmConfig,
    ProviderHttpError,
    ToolsUnsupportedError,
    VisionUnsupportedError,
    chat,
    generate,
    list_models,
)
from vera_app.modes import Mode, load_modes, resolve_mode

Request = dict[str, Any]
Response = dict[str, Any]
Handler = Callable[[Request], Any]

DEFAULT_RAG_INSTRUCTIONS = """You are VERA, a grounded document assistant.
Use only the cited evidence supplied in this prompt when answering.
Attach citation ids such as [C1] immediately after each claim they support.
Write citation ids as plain text — never inside backticks or other code formatting.
If the evidence is incomplete, say what is missing instead of guessing.
If cited evidence conflicts, describe the conflict and cite both sides.
Do not cite sources that are not present in the evidence list.
If tools are available, use them only to retrieve, verify, or inspect source-grounded information before answering."""


def _open_document(path: str) -> VeraDocument:
    return VeraDocument.open(path)


def _open_corpus(path: str, request: Request) -> VeraCorpus:
    recursive_value = request.get("recursive")
    recursive = None if recursive_value is None else bool(recursive_value)
    excludes_value = request.get("excludes")
    excludes = (
        [str(value) for value in excludes_value if str(value).strip()]
        if isinstance(excludes_value, list)
        else None
    )
    return VeraCorpus.open(
        path,
        recursive=recursive,
        excludes=excludes,
        default_recursive=bool(request.get("default_recursive", False)),
        allow_empty=bool(request.get("allow_empty", False)),
    )


def _resolve_target(request: Request):
    """Open the search/inspect target for a request.

    Returns a VeraCorpus when multiple paths are selected or the path is a
    directory; otherwise a single VeraDocument. Single-file selection keeps
    the original single-document code path.
    """
    paths = request.get("paths")
    if isinstance(paths, list):
        files = [str(p) for p in paths if str(p).strip()]
        if len(files) > 1:
            return VeraCorpus.from_paths(files)
        if len(files) == 1:
            return _open_corpus(files[0], request) if Path(files[0]).is_dir() else _open_document(files[0])
    path = str(request["path"])
    return _open_corpus(path, request) if Path(path).is_dir() else _open_document(path)


def _scoped_single_file(request: Request) -> str | None:
    """Return the source path when a request is scoped to exactly one file.

    Single-document search results don't carry a `file` field (unlike corpus
    results), but the UI needs it to locate and highlight the source when the
    search was scoped via checkbox rather than an opened document. Returns the
    explicit single path, or the request `path` when it points at a file.
    """
    paths = request.get("paths")
    if isinstance(paths, list):
        files = [str(p) for p in paths if str(p).strip()]
        if len(files) == 1:
            return None if Path(files[0]).is_dir() else files[0]
        if len(files) > 1:
            return None
    path = str(request.get("path") or "")
    if path and not Path(path).is_dir():
        return path
    return None



def _figure_payload(figure: dict[str, Any]) -> dict[str, Any]:
    data = figure.pop("data", None)
    if data is not None:
        mime_type = figure.get("mime_type") or "application/octet-stream"
        figure["data_url"] = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
    return figure


def _result_payload(result: Any) -> dict[str, Any]:
    data = result.as_dict()
    metadata = data.pop("metadata", {})
    payload = {**metadata, **data}
    for key in ("before_chunks", "after_chunks"):
        if key in payload:
            payload[key] = [
                {**item.pop("metadata", {}), **item}
                for item in payload[key]
            ]
    return payload


class _AnswerStream:
    """Publish answer text incrementally without exposing inline tool syntax."""

    _TOOL_MARKERS = ("<tool_call", "<functions.")

    def __init__(self, write_event: Callable[[dict[str, Any]], None] | None):
        self._write_event = write_event
        self._pending = ""
        self._visible = ""
        self._blocked = False

    @property
    def callback(self) -> Callable[[str], None] | None:
        return self.feed if self._write_event else None

    def feed(self, text: str) -> None:
        if not text or not self._write_event or self._blocked:
            return
        self._pending += text
        while self._pending:
            marker_start = self._pending.find("<")
            if marker_start < 0:
                self._emit(self._pending)
                self._pending = ""
                return
            if marker_start:
                self._emit(self._pending[:marker_start])
                self._pending = self._pending[marker_start:]
            lowered = self._pending.lower()
            if any(marker.startswith(lowered) for marker in self._TOOL_MARKERS):
                return
            if any(lowered.startswith(marker) for marker in self._TOOL_MARKERS):
                self._pending = ""
                self._blocked = True
                return
            self._emit(self._pending[0])
            self._pending = self._pending[1:]

    def finish(self, response: ChatResponse) -> None:
        """Reconcile streamed text with the provider's parsed canonical response."""
        if not self._write_event:
            return
        if response.tool_calls:
            if self._visible:
                self._write_event({"event": "answer_reset"})
            return
        if not self._blocked and self._pending:
            self._emit(self._pending)
            self._pending = ""
        if not self._blocked and self._visible.strip() == response.content:
            return
        if self._visible:
            self._write_event({"event": "answer_reset"})
        if response.content:
            self._write_event({"event": "answer_delta", "text": response.content})

    def abandon(self) -> None:
        """Discard a partial attempt before retrying the provider request."""
        if self._write_event and self._visible:
            self._write_event({"event": "answer_reset"})

    def _emit(self, text: str) -> None:
        if not text or not self._write_event:
            return
        self._visible += text
        self._write_event({"event": "answer_delta", "text": text})


def _inspect(
    request: Request,
    write_event=None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    path = str(request["path"])
    if Path(path).is_dir():
        corpus = _open_corpus(path, request)
        try:
            if request.get("summary_only"):
                result = corpus.inspect_summary()
                if cancel:
                    cancel.raise_if_cancelled()
                return result

            def report_progress(update: dict[str, Any]) -> None:
                if cancel:
                    cancel.raise_if_cancelled()
                if write_event:
                    write_event({"event": "inspection_progress", **update})

            return corpus.inspect(
                progress=report_progress if write_event or cancel else None,
            )
        finally:
            corpus.close()
    doc = _open_document(path)
    try:
        result = doc.inspect()
        if cancel:
            cancel.raise_if_cancelled()
        return result
    finally:
        doc.close()


def _validate(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        return doc.validate()
    finally:
        doc.close()


def _index_status(request: Request) -> dict[str, Any]:
    return library_index_status(
        str(request["path"]),
        verify_hashes=bool(request.get("verify_hashes", True)),
    )


def _index_build(request: Request, write_event=None) -> dict[str, Any]:
    def report_progress(update: dict[str, Any]) -> None:
        if write_event:
            write_event({"event": "index_progress", **update})

    excludes = request.get("excludes")
    return build_library_index(
        str(request["path"]),
        recursive=bool(request.get("recursive", True)),
        excludes=[str(value) for value in excludes] if isinstance(excludes, list) else (),
        progress=report_progress,
    )


def _index_update(request: Request, write_event=None) -> dict[str, Any]:
    def report_progress(update: dict[str, Any]) -> None:
        if write_event:
            write_event({"event": "index_progress", **update})

    return update_library_index(str(request["path"]), progress=report_progress)


def _search(request: Request) -> list[dict[str, Any]]:
    target = _resolve_target(request)
    # When the search is scoped to a single file, stamp each result with its
    # source path so the UI can open/highlight it (corpus results already carry
    # `file`; single-document results otherwise don't).
    scoped_file = _scoped_single_file(request)
    try:
        results = target.search(
            text=str(request.get("query", "")),
            mode=str(request.get("mode", "hybrid")),
            top_k=int(request.get("top_k", 10)),
            context_chunks=int(request.get("context_chunks", 0)),
        )
        include_regions = bool(request.get("include_regions", False))
        include_figures = bool(request.get("include_figures", False))
        include_figure_data = bool(request.get("include_figure_data", False))
        payload: list[dict[str, Any]] = []
        for result in results:
            entry = _result_payload(result)
            if scoped_file and not entry.get("file"):
                entry["file"] = scoped_file
            document = (
                target.document(result.file)
                if isinstance(target, VeraCorpus)
                else target
            )
            if include_regions:
                entry["regions"] = regions_for(document, result)
            if include_figures:
                entry["figures"] = [
                    _figure_payload(figure)
                    for figure in figures_for(
                        document,
                        result,
                        include_data=include_figure_data,
                    )
                ]
            payload.append(entry)
        return payload
    finally:
        target.close()


def _figure_data(request: Request) -> list[dict[str, Any]]:
    """Return image payloads for explicitly selected figure attachments."""
    raw_ids = request.get("asset_ids")
    asset_ids = (
        list(dict.fromkeys(str(value) for value in raw_ids if str(value).strip()))
        if isinstance(raw_ids, list)
        else []
    )
    if not asset_ids:
        return []
    doc = _open_document(str(request["path"]))
    try:
        return [
            _figure_payload(figure)
            for figure in figures(
                doc,
                include_data=True,
                attachment_ids=asset_ids,
            )
        ]
    finally:
        doc.close()


def _compact_text(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def _redact_messages_for_trace(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deep-copy `messages` with image_url data replaced by a short placeholder.

    Figure images can be several hundred KB of base64; embedding them verbatim in
    the trace would bloat the IPC payload and the session store for no benefit
    (the trace is a debug view, not something that needs to re-render the image).
    """
    redacted = copy.deepcopy(messages)
    for message in redacted:
        # Responses API replay items may contain large encrypted reasoning blobs.
        # They are required for the next model call but add no value to the UI trace.
        message.pop("_responses_items", None)
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            url = str((part.get("image_url") or {}).get("url") or "")
            size = len(url)
            part["image_url"] = {"url": f"<image omitted, {size} bytes>"}
    return redacted


def _count_image_parts(messages: list[dict[str, Any]]) -> int:
    """Count image_url content parts across `messages`.

    Used to report how many images actually ended up in the final request sent
    to the LLM — reflects reality even if some were dropped along the way (e.g.
    `_strip_image_parts` after a `VisionUnsupportedError`).
    """
    total = 0
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        total += sum(1 for part in content if isinstance(part, dict) and part.get("type") == "image_url")
    return total


def _clear_figure_context_flags(citations: list[dict[str, Any]]) -> None:
    for citation in citations:
        for figure in (citation.get("result") or {}).get("figures") or []:
            figure.pop("included_in_context", None)


def _instructions(request: Request, mode: Mode) -> str:
    base = mode.instructions.strip() or DEFAULT_RAG_INSTRUCTIONS
    custom = str(request.get("instructions", "") or "").strip()
    if not custom or custom == base:
        return base
    return f"{base}\n\nAdditional response instructions:\n{custom}"


SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "search",
        "description": (
            "Search the open VERA document or corpus for passages relevant to a query. "
            "Call this as many times as needed (refining the query, mode, or breadth) "
            "to gather evidence before answering. Returns ranked passages, each with a "
            "citation id you must reuse when citing."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language or keyword query to retrieve passages for.",
                },
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "semantic", "keyword"],
                    "description": "Retrieval strategy. hybrid is the best default; keyword for exact phrases/ids; semantic for paraphrased questions.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "description": "How many passages to return.",
                },
                "context_chunks": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 3,
                    "description": "Adjacent chunks of surrounding context to include around each hit.",
                },
                "include_figures": {
                    "type": "boolean",
                    "description": "Include nearby figure/table metadata (use for charts, diagrams, tables).",
                },
                "quality": {
                    "type": "string",
                    "enum": ["strict", "balanced", "permissive"],
                    "description": (
                        "How aggressively to drop weaker matches relative to the best hit. "
                        "strict = only the closest matches; balanced = the default; "
                        "permissive = keep almost everything. If a search returns too few "
                        "passages, retry with a more permissive quality."
                    ),
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def _resolve_mode(request: Request) -> Mode:
    return resolve_mode(
        str(request.get("mode_id") or "") or None,
        str(request.get("modes_dir") or "") or None,
    )


def _list_modes(request: Request) -> dict[str, Any]:
    return {"modes": [mode.to_dict() for mode in load_modes(str(request.get("modes_dir") or "") or None)]}


def _prior_citation_labels(request: Request) -> tuple[dict[str, str], int]:
    """Build a stable chunk_id -> citation id map from earlier turns.

    Returns the registry plus the highest numeric id used so far, so new chunks
    continue numbering after it and previously-cited chunks keep their original id.
    """
    registry: dict[str, str] = {}
    max_index = 0
    raw = request.get("prior_citations")
    if not isinstance(raw, list):
        return registry, max_index
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        citation_id = str(entry.get("id") or "").strip()
        chunk_id = str(entry.get("chunk_id") or "").strip()
        if not citation_id or not chunk_id:
            continue
        registry.setdefault(chunk_id, citation_id)
        match = re.fullmatch(r"C(\d+)", citation_id)
        if match:
            max_index = max(max_index, int(match.group(1)))
    return registry, max_index


class _SearchTool:
    """Executes the model's `search` calls and accumulates citations."""

    # Relative score cutoffs as a fraction of the best hit in each search.
    # VERA's hybrid/keyword scores are RRF-based (not 0-1 cosine), so an absolute
    # threshold is unreliable; a per-search relative cutoff is mode-agnostic.
    _QUALITY_RATIOS = {"strict": 0.85, "balanced": 0.55, "permissive": 0.0}

    def __init__(self, request: Request, mode: Mode, write_event=None, label_registry: dict[str, str] | None = None, label_start: int = 0) -> None:
        self._request = request
        self._mode = mode
        self._by_chunk: dict[str, dict[str, Any]] = {}
        self.citations: list[dict[str, Any]] = []
        self.searches: list[dict[str, Any]] = []
        self._write_event = write_event
        # Session-wide label registry: chunk_id -> citation id (e.g. "C2"). Seeded
        # from prior turns so the same chunk keeps its id across the conversation.
        self._label_registry: dict[str, str] = dict(label_registry or {})
        self._label_counter = label_start
        # Bounds how many figure images get offered to the LLM across the whole
        # answer (not just one search call) so a chatty agent loop can't blow up
        # the prompt with dozens of images.
        self._image_budget = mode.max_figure_images
        self._pending_image_parts: list[dict[str, Any]] = []

    @property
    def chunk_count(self) -> int:
        return len(self.citations)

    def take_pending_image_parts(self) -> list[dict[str, Any]]:
        """Pop and return image/text content parts queued since the last call."""
        parts, self._pending_image_parts = self._pending_image_parts, []
        return parts

    def _register(self, result: dict[str, Any]) -> str:
        chunk_id = str(result.get("chunk_id") or f"chunk_{len(self._by_chunk)}")
        existing = self._by_chunk.get(chunk_id)
        if existing is not None:
            return str(existing["id"])
        # Reuse a stable session-wide label if this chunk was cited in a prior turn;
        # otherwise allocate the next id after the highest one used so far.
        citation_id = self._label_registry.get(chunk_id)
        if citation_id is None:
            self._label_counter += 1
            citation_id = f"C{self._label_counter}"
            self._label_registry[chunk_id] = citation_id
        page = result.get("page_start") or result.get("page_end") or "-"
        entry = {
            "id": citation_id,
            "label": f"[{citation_id}] p. {page}",
            "result": result,
        }
        self.citations.append(entry)
        self._by_chunk[chunk_id] = entry
        return citation_id

    def run(self, arguments: dict[str, Any]) -> dict[str, Any]:
        remaining = self._mode.max_chunks - self.chunk_count
        if remaining <= 0:
            return {"error": "Chunk budget exhausted; answer with the evidence already gathered."}
        query = str(arguments.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}
        top_k = min(int(arguments.get("top_k", self._mode.top_k) or self._mode.top_k), remaining)
        top_k = max(1, min(20, top_k))
        search_mode = str(arguments.get("mode", self._mode.search_mode) or self._mode.search_mode)
        if search_mode not in {"hybrid", "semantic", "keyword"}:
            search_mode = self._mode.search_mode
        context_chunks = arguments.get("context_chunks", self._mode.context_chunks)
        include_figures = bool(arguments.get("include_figures", self._mode.include_figures))
        quality = str(arguments.get("quality", "balanced") or "balanced").lower()
        if quality not in self._QUALITY_RATIOS:
            quality = "balanced"
        if self._write_event:
            self._write_event({"event": "search_start", "query": query, "mode": search_mode, "top_k": top_k})
        results = _search({
            **self._request,
            "query": query,
            "mode": search_mode,
            "top_k": top_k,
            "context_chunks": max(0, min(3, int(context_chunks or 0))),
            "include_regions": True,
            "include_figures": include_figures,
            # Fetch actual image bytes (not just captions) so citations carry a
            # `data_url` the UI can render and so we can offer images to the LLM.
            "include_figure_data": include_figures,
        })
        # Relative quality filter: drop hits far weaker than the best one.
        if results:
            top_score = max(float(r.get("score") or 0.0) for r in results)
            ratio = self._QUALITY_RATIOS[quality]
            if top_score > 0 and ratio > 0:
                cutoff = top_score * ratio
                kept = [r for r in results if float(r.get("score") or 0.0) >= cutoff]
                results = kept or results[:1]
        passages = []
        skipped_cited = 0
        for result in results:
            chunk_id = str(result.get("chunk_id") or "")
            # Dedup: skip passages already retrieved earlier so re-searches surface
            # fresh evidence (the model still has the originals in prior tool output).
            if chunk_id and chunk_id in self._by_chunk:
                skipped_cited += 1
                continue
            citation_id = self._register(result)
            passage: dict[str, Any] = {
                "citation": citation_id,
                "page_start": result.get("page_start"),
                "page_end": result.get("page_end"),
                "heading_path": result.get("heading_path"),
                "text": _compact_text(str(result.get("text", "")), limit=4000),
            }
            before = result.get("before_chunks") or []
            after = result.get("after_chunks") or []
            if before:
                passage["context_before"] = [
                    _compact_text(str(chunk.get("text", "")), limit=2000) for chunk in before
                ]
            if after:
                passage["context_after"] = [
                    _compact_text(str(chunk.get("text", "")), limit=2000) for chunk in after
                ]
            if include_figures and result.get("figures"):
                passage["figures"] = [
                    {"caption": fig.get("caption"), "page": fig.get("page_number")}
                    for fig in result.get("figures", [])
                ]
                # Queue the actual images (bounded by the remaining budget) so the
                # agent loop can show them to the LLM alongside this citation.
                for fig in result.get("figures", []):
                    data_url = fig.pop("data_url", None)
                    if self._image_budget <= 0 or not data_url:
                        continue
                    fig["included_in_context"] = True
                    page = fig.get("page_number") or result.get("page_start") or "-"
                    caption = fig.get("caption") or "no caption"
                    self._pending_image_parts.append(
                        {"type": "text", "text": f"Figure for [{citation_id}] (p. {page}): {caption}"}
                    )
                    self._pending_image_parts.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                    self._image_budget -= 1
            passages.append(passage)
        self.searches.append({"query": query, "mode": search_mode, "top_k": top_k, "hits": len(passages)})
        if self._write_event:
            self._write_event({"event": "search_done", "query": query, "mode": search_mode, "hits": len(passages)})
        if not passages:
            if skipped_cited:
                note = (
                    "Every match was already retrieved earlier in this conversation. "
                    "Broaden the query or try quality='permissive'."
                )
            else:
                note = "No passages matched; try different terms, mode, or quality='permissive'."
            return {"query": query, "passages": [], "note": note}
        response: dict[str, Any] = {"query": query, "passages": passages}
        if skipped_cited:
            response["note"] = f"{skipped_cited} already-retrieved passage(s) omitted as duplicates."
        return response


def _retrieval_payload(request: Request, mode: Mode, instructions: str) -> dict[str, Any]:
    """Non-agentic fallback: one search, then synthesize (or list passages)."""
    prompt = str(request.get("prompt", "")).strip()
    results = _search({
        **request,
        "query": prompt,
        "mode": mode.search_mode,
        "top_k": mode.top_k,
        "context_chunks": mode.context_chunks,
        "include_regions": True,
        "include_figures": mode.include_figures,
        # Fetch actual image bytes too (not just captions), same as the agentic
        # path, so this fallback can also offer figure images to the model.
        "include_figure_data": mode.include_figures,
    })
    citations = []
    label_registry, label_index = _prior_citation_labels(request)
    # Mirrors _SearchTool.run()'s image-part queueing, bounded by the same
    # per-answer image budget.
    image_parts: list[dict[str, Any]] = []
    image_budget = mode.max_figure_images
    for result in results:
        chunk_id = str(result.get("chunk_id") or "")
        citation_id = label_registry.get(chunk_id)
        if citation_id is None:
            label_index += 1
            citation_id = f"C{label_index}"
            if chunk_id:
                label_registry[chunk_id] = citation_id
        page = result.get("page_start") or result.get("page_end") or "-"
        citations.append({
            "id": citation_id,
            "label": f"[{citation_id}] p. {page}",
            "result": result,
        })
        if mode.include_figures:
            for fig in result.get("figures") or []:
                data_url = fig.pop("data_url", None)
                if image_budget <= 0 or not data_url:
                    continue
                fig["included_in_context"] = True
                fig_page = fig.get("page_number") or page
                caption = fig.get("caption") or "no caption"
                image_parts.append(
                    {"type": "text", "text": f"Figure for [{citation_id}] (p. {fig_page}): {caption}"}
                )
                image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                image_budget -= 1
    evidence = "\n".join(
        f"[{citation['id']}] {citation['result'].get('text', '')}" for citation in citations
    )
    llm_prompt = (
        f"Instructions:\n{instructions}\n\n"
        f"User question:\n{prompt}\n\nEvidence:\n{evidence}"
    )
    return {
        "prompt": prompt,
        "citations": citations,
        "instructions": instructions,
        "llm_prompt": llm_prompt,
        "image_parts": image_parts,
    }


def _user_attachment_parts(request: Request) -> list[dict[str, Any]]:
    """Build image content parts from images the user attached to this message."""
    attachments = request.get("attachments")
    if not isinstance(attachments, list):
        return []
    parts: list[dict[str, Any]] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        data_url = attachment.get("data_url")
        if not data_url:
            continue
        parts.append({"type": "image_url", "image_url": {"url": str(data_url)}})
    return parts


def _strip_image_parts(messages: list[dict[str, Any]]) -> None:
    """In-place: collapse any multimodal (list-content) message back to plain text.

    Called once a provider signals it can't accept image input (`VisionUnsupportedError`)
    so a retry doesn't hit the same rejection again — regardless of whether the images
    came from user attachments, cited figures, or both.
    """
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        text = "\n".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
        had_images = any(isinstance(part, dict) and part.get("type") == "image_url" for part in content)
        if had_images:
            note = "[Images omitted: this model does not support image input.]"
            text = f"{text}\n{note}" if text else note
        message["content"] = text


def _answer(
    request: Request,
    write_event=None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    prompt = str(request.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("prompt is required")

    mode = _resolve_mode(request)
    instructions = _instructions(request, mode)
    config = LlmConfig.from_request(request.get("llm"))
    if not config.enabled:
        raise ValueError("An LLM model must be selected to answer.")

    # Build conversation history from prior turns (multi-turn support).
    # Each entry: {"role": "user"|"assistant", "content": str}
    history: list[dict[str, Any]] = []
    raw_history = request.get("history")
    if isinstance(raw_history, list):
        for entry in raw_history:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role", ""))
            content = str(entry.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                history.append({"role": role, "content": content})

    # Collect a structured trace of every LLM request/response and search/tool
    # call so the completed trace matches the events shown while answering.
    trace: list[dict[str, Any]] = []

    def record(entry: dict[str, Any]) -> None:
        trace.append(entry)
        if write_event:
            write_event(entry)

    # Seed the citation labeller with ids already assigned in earlier turns so the
    # same chunk keeps its `[C#]` id across the whole session.
    label_registry, label_start = _prior_citation_labels(request)
    tool = _SearchTool(request, mode, write_event=record, label_registry=label_registry, label_start=label_start)
    # Images the user attached to this message (via the composer's attach button
    # or drag-and-drop) ride along in the initial user message, alongside any
    # figure images the agent surfaces later while searching.
    attachment_parts = _user_attachment_parts(request)
    user_content: Any = prompt
    if attachment_parts:
        user_content = [{"type": "text", "text": prompt}, *attachment_parts]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instructions},
        *history,
        {"role": "user", "content": user_content},
    ]

    last_response: ChatResponse | None = None
    # Whether the active provider still appears to accept image content. Flipped
    # off for the rest of this answer the first time it rejects an image message
    # (auto-detected — there's no per-provider "supports vision" setting).
    vision_available = True
    vision_fallback = False
    try:
        # One extra turn beyond the search budget lets the model write its final answer.
        for turn in range(mode.max_searches + 1):
            if cancel:
                cancel.raise_if_cancelled()
            force_answer = turn >= mode.max_searches or tool.chunk_count >= mode.max_chunks
            offered_tools = None if force_answer else [SEARCH_TOOL]
            answer_stream = _AnswerStream(write_event)
            record({
                "event": "llm_request",
                "turn": turn,
                "model": config.model,
                "tools": [t["function"]["name"] for t in (offered_tools or [])],
                "messages": _redact_messages_for_trace(messages),
            })
            try:
                response = chat(
                    messages,
                    config,
                    tools=offered_tools,
                    tool_choice="auto",
                    on_delta=answer_stream.callback,
                    **({"cancel": cancel} if cancel else {}),
                )
            except VisionUnsupportedError:
                # Neutralize every image-bearing message (user attachments and/or
                # figure images) and retry this turn once, text-only, without ever
                # offering images again this answer.
                answer_stream.abandon()
                answer_stream = _AnswerStream(write_event)
                _strip_image_parts(messages)
                vision_available = False
                vision_fallback = True
                response = chat(
                    messages,
                    config,
                    tools=offered_tools,
                    tool_choice="auto",
                    on_delta=answer_stream.callback,
                    **({"cancel": cancel} if cancel else {}),
                )
            if cancel:
                cancel.raise_if_cancelled()
            answer_stream.finish(response)
            last_response = response
            record({
                "event": "llm_response",
                "turn": turn,
                "model": response.model,
                "content": response.content,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in response.tool_calls
                ],
                "usage": response.usage,
            })
            print(
                f"[vera-answer] turn={turn} force_answer={force_answer} "
                f"tool_calls={len(response.tool_calls)} content_len={len(response.content)} "
                f"citations={tool.chunk_count}",
                file=sys.stderr,
                flush=True,
            )
            if force_answer or not response.tool_calls:
                break
            # Build the assistant message to append — ensure content is not None.
            assistant_msg = dict(response.message)
            if assistant_msg.get("content") is None:
                assistant_msg["content"] = ""
            messages.append(assistant_msg)
            for call in response.tool_calls:
                if cancel:
                    cancel.raise_if_cancelled()
                output = tool.run(call.arguments) if call.name == "search" else {"error": f"Unknown tool: {call.name}"}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(output),
                })
                record({
                    "event": "tool_call",
                    "turn": turn,
                    "name": call.name,
                    "arguments": call.arguments,
                    "output": output,
                })
            # If any of this turn's searches surfaced figures within the image
            # budget, offer them to the model as a follow-up multimodal message so
            # it can actually see the images (not just their captions).
            if vision_available:
                image_parts = tool.take_pending_image_parts()
                if image_parts:
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Reference images for the figures cited above:"},
                            *image_parts,
                        ],
                    })
            print(
                f"[vera-answer]   -> appended tool results, messages now {len(messages)}, "
                f"total citations: {tool.chunk_count}",
                file=sys.stderr,
                flush=True,
            )
    except ToolsUnsupportedError:
        # Provider can't do tool-calling: fall back to one-shot retrieve-then-answer.
        answer_stream.abandon()
        fallback = _retrieval_payload(request, mode, instructions)
        fallback_user_content: Any = fallback["llm_prompt"]
        if attachment_parts:
            fallback_user_content = [{"type": "text", "text": fallback["llm_prompt"]}, *attachment_parts]
        fallback_messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": fallback_user_content},
        ]
        if fallback["image_parts"]:
            fallback_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": "Reference images for the figures cited above:"},
                    *fallback["image_parts"],
                ],
            })
        record({
            "event": "llm_request",
            "turn": 0,
            "model": config.model,
            "tools": [],
            "messages": _redact_messages_for_trace(fallback_messages),
        })
        fallback_stream = _AnswerStream(write_event)
        try:
            llm_result = generate(
                fallback_messages,
                config,
                on_delta=fallback_stream.callback,
                **({"cancel": cancel} if cancel else {}),
            )
        except VisionUnsupportedError:
            # This provider also can't take image input; retry once, text-only.
            fallback_stream.abandon()
            fallback_stream = _AnswerStream(write_event)
            _strip_image_parts(fallback_messages)
            vision_fallback = True
            llm_result = generate(
                fallback_messages,
                config,
                on_delta=fallback_stream.callback,
                **({"cancel": cancel} if cancel else {}),
            )
        fallback_stream.finish(
            ChatResponse(
                content=llm_result.answer,
                tool_calls=[],
                message={"role": "assistant", "content": llm_result.answer},
                model=llm_result.model,
                usage=llm_result.usage,
            )
        )
        record({
            "event": "llm_response",
            "turn": 0,
            "model": llm_result.model,
            "content": llm_result.answer,
            "tool_calls": [],
            "usage": llm_result.usage,
        })
        images_sent = _count_image_parts(fallback_messages)
        if images_sent == 0:
            _clear_figure_context_flags(fallback["citations"])
        return {
            "prompt": prompt,
            "answer": llm_result.answer,
            "citations": fallback["citations"],
            "instructions": instructions,
            "mode": mode.id,
            "mode_label": mode.label,
            "answer_mode": "retrieval",
            "searches": [],
            "trace": trace,
            "images_sent": images_sent,
            "vision_fallback": vision_fallback,
            "llm": {"provider": llm_result.provider, "model": llm_result.model, "usage": llm_result.usage},
        }

    answer = last_response.content if last_response else ""
    if not answer and tool.citations:
        # The model returned empty content on the final turn (common when the tool
        # budget runs out and tools are dropped from the payload, leaving some models
        # momentarily confused).  Send a short nudge to get the synthesis.
        nudge_stream = _AnswerStream(write_event)
        try:
            nudge_messages = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Based on the passages retrieved above, please answer "
                        "the original question now. Attach citation ids."
                    ),
                },
            ]
            record({
                "event": "llm_request",
                "turn": mode.max_searches + 1,
                "model": config.model,
                "tools": [],
                "messages": _redact_messages_for_trace(nudge_messages),
            })
            nudge = chat(
                nudge_messages,
                config,
                tools=None,
                tool_choice="auto",
                on_delta=nudge_stream.callback,
                **({"cancel": cancel} if cancel else {}),
            )
            nudge_stream.finish(nudge)
            record({
                "event": "llm_response",
                "turn": mode.max_searches + 1,
                "model": nudge.model,
                "content": nudge.content,
                "tool_calls": [],
                "usage": nudge.usage,
            })
            answer = nudge.content
            if nudge.model:
                last_response = nudge
        except CancelledError:
            raise
        except Exception:
            nudge_stream.abandon()
            pass
    if not answer:
        answer = "I could not produce an answer from the selected VERA source."
    images_sent = _count_image_parts(messages)
    if images_sent == 0:
        _clear_figure_context_flags(tool.citations)
    return {
        "prompt": prompt,
        "answer": answer,
        "citations": tool.citations,
        "instructions": instructions,
        "mode": mode.id,
        "mode_label": mode.label,
        "answer_mode": "agent",
        "searches": tool.searches,
        "trace": trace,
        "images_sent": images_sent,
        "vision_fallback": vision_fallback,
        "llm": {
            "provider": "openai_compatible",
            "model": last_response.model if last_response else config.model,
            "usage": last_response.usage if last_response else None,
        },
    }



def _convert(
    request: Request,
    write_event=None,
    cancel: CancellationToken | None = None,
) -> dict[str, str]:
    input_path = str(request["input"])
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 0,
                "total": 1,
                "input": input_path,
            }
        )
    output = convert(
        input_path,
        str(request["output"]),
        model=str(request.get("model", "hashing")),
        parser=str(request.get("parser", "pymupdf")),
        chunk_size=int(request.get("chunk_size", 500)),
        overlap=int(request.get("overlap", 75)),
        store_original=bool(request.get("store_original", True)),
        ocr_mode=str(request.get("ocr_mode", "auto")),
        ocr_language=str(request.get("ocr_language", "eng")),
        ocr_dpi=int(request.get("ocr_dpi", 300)),
        cancel=cancel,
    )
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 1,
                "total": 1,
                "input": input_path,
            }
        )
    return {"output": output}


def _batch_convert(
    request: Request,
    write_event=None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    def report_progress(completed: int, total: int, input_path: str) -> None:
        if cancel:
            cancel.raise_if_interrupted()
        if write_event:
            write_event(
                {
                    "event": "conversion_progress",
                    "completed": completed,
                    "total": total,
                    "input": input_path,
                }
            )

    raw_paths = request.get("paths")
    paths: list[str] | None = None
    if isinstance(raw_paths, list):
        paths = [str(item) for item in raw_paths if str(item).strip()]
        if not paths:
            paths = None

    directory = request.get("directory")
    progress_label = (
        f"{len(paths)} selected PDF{'s' if len(paths) != 1 else ''}"
        if paths is not None
        else str(directory or "")
    )
    if write_event:
        write_event(
            {
                "event": "conversion_progress",
                "completed": 0,
                "total": 0,
                "input": progress_label,
                "phase": "discovering",
            }
        )
    if cancel:
        cancel.raise_if_interrupted()

    return batch_convert(
        None if paths is not None else str(directory),
        paths=paths,
        recursive=bool(request.get("recursive", True)),
        overwrite=bool(request.get("overwrite", False)),
        model=str(request.get("model", "hashing")),
        parser=str(request.get("parser", "pymupdf")),
        chunk_size=int(request.get("chunk_size", 500)),
        overlap=int(request.get("overlap", 75)),
        store_original=bool(request.get("store_original", True)),
        ocr_mode=str(request.get("ocr_mode", "auto")),
        ocr_language=str(request.get("ocr_language", "eng")),
        ocr_dpi=int(request.get("ocr_dpi", 300)),
        progress=report_progress,
        cancel=cancel,
    )


def _export(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        output = export_source_document(
            doc,
            str(request["output"]) if request.get("output") else None,
        )
        source = get_source_document(doc)
        return {
            "output": output,
            "filename": source.filename,
            "mime_type": source.media_type,
            "hash": source.checksum,
        }
    finally:
        doc.close()


def _source_cache_dir(request: Request) -> Path:
    """Return the directory used to materialize embedded source documents.

    Electron passes a stable userData cache dir so the main process can serve
    files over a privileged ``vera-source:`` protocol without shipping PDF
    bytes through the JSON-Lines IPC channel (which freezes the UI on large
    documents). Tests and other callers fall back to the system temp dir.
    """
    configured = request.get("cache_dir")
    if isinstance(configured, str) and configured.strip():
        return Path(configured)
    return Path(tempfile.gettempdir()) / "vera-source-cache"


def _materialize_source_cache(
    source: AttachmentRecord,
    cache_dir: Path,
    cancel: CancellationToken | None = None,
) -> Path:
    """Write source bytes to a hash-keyed cache file; reuse when unchanged."""
    if cancel:
        cancel.raise_if_cancelled()
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = str(source.checksum or hashlib.sha256(source.data).hexdigest())
    suffix = Path(source.filename or "source.bin").suffix or ".bin"
    # Keep the digest filesystem-safe (checksums are typically hex already).
    safe_digest = re.sub(r"[^A-Za-z0-9._-]", "_", digest)
    cache_path = cache_dir / f"{safe_digest}{suffix}"
    if cache_path.is_file() and cache_path.stat().st_size == len(source.data):
        return cache_path
    tmp_path = cache_path.with_name(f"{cache_path.name}.{threading.get_ident()}.tmp")
    try:
        tmp_path.write_bytes(source.data)
        if cancel:
            cancel.raise_if_cancelled()
        tmp_path.replace(cache_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return cache_path


def _source_from_pdf(
    path: Path,
    cache_dir: Path,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Materialize a filesystem PDF into the source cache for the document viewer."""
    if cancel:
        cancel.raise_if_cancelled()
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    data = path.read_bytes()
    if cancel:
        cancel.raise_if_cancelled()
    if not data.startswith(b"%PDF"):
        raise ValueError(f"Not a PDF file: {path}")
    source = AttachmentRecord(
        id="source_pdf",
        data=data,
        media_type="application/pdf",
        filename=path.name,
    )
    cache_path = _materialize_source_cache(source, cache_dir, cancel)
    return {
        "filename": source.filename,
        "mime_type": source.media_type,
        "hash": source.checksum,
        "size": len(source.data),
        "cache_path": str(cache_path),
    }


def _source(
    request: Request,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    path = Path(str(request["path"]))
    cache_dir = _source_cache_dir(request)
    if path.suffix.lower() == ".pdf":
        return _source_from_pdf(path, cache_dir, cancel)
    doc = _open_document(str(path))
    try:
        source = get_source_document(doc)
        if cancel:
            cancel.raise_if_cancelled()
        mime_type = source.media_type or "application/octet-stream"
        cache_path = _materialize_source_cache(source, cache_dir, cancel)
        return {
            "filename": source.filename,
            "mime_type": mime_type,
            "hash": source.checksum,
            "size": len(source.data),
            "cache_path": str(cache_path),
        }
    finally:
        doc.close()


def _page(request: Request) -> dict[str, Any] | None:
    doc = _open_document(str(request["path"]))
    try:
        return get_page(doc, int(request["page_number"]))
    finally:
        doc.close()


def _list_models(request: Request) -> dict[str, Any]:
    config = LlmConfig.from_request(request.get("llm"))
    models = list_models(config)
    return {"models": models}


HANDLERS: dict[str, Handler] = {
    "ping": lambda request: {"status": "ok"},
    "inspect": _inspect,
    "validate": _validate,
    "index_status": _index_status,
    "index_build": _index_build,
    "index_update": _index_update,
    "search": _search,
    "figure_data": _figure_data,
    "answer": _answer,
    "convert": _convert,
    "batch_convert": _batch_convert,
    "export": _export,
    "source": _source,
    "page": _page,
    "list_models": _list_models,
    "list_modes": _list_modes,
}

_stdout_lock = threading.Lock()
_inflight_lock = threading.Lock()
_inflight_requests: dict[str, CancellationToken] = {}


def _write_response(response: Response) -> None:
    with _stdout_lock:
        print(json.dumps(response), flush=True)


def _cancelled_error_message(action: str, exc: BaseException | None = None) -> str:
    if exc and str(exc):
        return str(exc)
    if action in {"convert", "batch_convert"}:
        return "Conversion cancelled"
    if action == "inspect":
        return "Inspection cancelled"
    if action == "source":
        return "Source loading cancelled"
    return "Answer cancelled"


def handle(request: Request, cancel: CancellationToken | None = None) -> Response:
    """Dispatch a JSON-RPC request from the Electron renderer.

    Args:
        request: Parsed request dict with ``action`` and optional ``params``.
        cancel: Optional token checked by long-running handlers.

    Returns:
        Response dict with ``id``, ``ok``, and result or error fields.
    """
    request_id = request.get("id")
    action = str(request.get("action", ""))
    try:
        if action not in HANDLERS:
            raise ValueError(f"Unknown action: {action}")
        if action == "answer":
            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})
            result = _answer(request, write_event=_emit, cancel=cancel)
        elif action in {"convert", "batch_convert"}:
            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})
            result = HANDLERS[action](request, write_event=_emit, cancel=cancel)
        elif action == "inspect":
            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})
            result = _inspect(request, write_event=_emit, cancel=cancel)
        elif action in {"index_build", "index_update"}:
            def _emit(data: dict[str, Any]) -> None:
                _write_response({**data, "id": request_id})
            result = HANDLERS[action](request, write_event=_emit)
        elif action == "source":
            result = _source(request, cancel=cancel)
        else:
            result = HANDLERS[action](request)
        return {"id": request_id, "ok": True, "result": result}
    except CancelledError as exc:
        return {
            "id": request_id,
            "ok": False,
            "error": _cancelled_error_message(action, exc),
            "cancelled": True,
        }
    except SkipCurrentError as exc:
        # Single-file convert has nothing to continue; treat skip like cancel.
        return {
            "id": request_id,
            "ok": False,
            "error": str(exc) or "File skipped",
            "cancelled": True,
        }
    except Exception as exc:
        if cancel and cancel.cancelled:
            return {
                "id": request_id,
                "ok": False,
                "error": _cancelled_error_message(action, exc if isinstance(exc, CancelledError) else None),
                "cancelled": True,
            }
        response: Response = {
            "id": request_id,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
        if isinstance(exc, ProviderHttpError):
            response["provider_error_detail"] = exc.raw_detail
        return response


def _run_cancellable_request(
    request: Request,
    request_id: str,
    cancel: CancellationToken,
) -> None:
    try:
        _write_response(handle(request, cancel=cancel))
    finally:
        with _inflight_lock:
            _inflight_requests.pop(request_id, None)


def _run_background_request(request: Request) -> None:
    _write_response(handle(request))


def main() -> int:
    """Read JSON-RPC requests from stdin and write responses to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: Response = {"id": None, "ok": False, "error": str(exc)}
        else:
            action = str(request.get("action", ""))
            if action == "cancel":
                target_id = str(request.get("target_id") or "")
                with _inflight_lock:
                    cancel = _inflight_requests.get(target_id)
                if cancel:
                    cancel.cancel()
                response = {
                    "id": request.get("id"),
                    "ok": True,
                    "result": {"target_id": target_id, "cancelled": bool(cancel)},
                }
            elif action == "skip":
                target_id = str(request.get("target_id") or "")
                with _inflight_lock:
                    cancel = _inflight_requests.get(target_id)
                if cancel:
                    cancel.skip()
                response = {
                    "id": request.get("id"),
                    "ok": True,
                    "result": {"target_id": target_id, "skipped": bool(cancel)},
                }
            elif action in {
                "answer",
                "convert",
                "batch_convert",
                "inspect",
                "index_build",
                "index_update",
                "source",
            }:
                request_id = str(request.get("id") or "")
                if not request_id:
                    response = {
                        "id": None,
                        "ok": False,
                        "error": f"{action} requests require an id",
                    }
                else:
                    if action in {"answer", "convert", "batch_convert", "inspect", "source"}:
                        cancel = CancellationToken()
                        with _inflight_lock:
                            _inflight_requests[request_id] = cancel
                        target = _run_cancellable_request
                        args: tuple[Any, ...] = (request, request_id, cancel)
                    else:
                        target = _run_background_request
                        args = (request,)
                    threading.Thread(target=target, args=args, daemon=True).start()
                    continue
            else:
                response = handle(request)
        _write_response(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
