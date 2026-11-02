"""Answer/chat sidecar handlers: agentic search, retrieval fallback, and modes."""

from __future__ import annotations

import copy
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from vera_app.agent_tools import AgentTool, ToolContext, ToolTable, allowlisted
from vera_app.cancellation import CancellationToken, CancelledError
from vera_app.chat_attachments import (
    SEARCH_ATTACHMENTS_TOOL,
    VIEW_FIGURE_TOOL,
    attachment_rows,
    attachment_usage,
    build_attachment_prompt,
    delivery_for,
    register_attachments,
    searchable_paths,
)
from vera_app.citations import CitationRegistry, evidence_block, evidence_token_budget
from vera_app.documents import scoped_single_file
from vera_app.llm import (
    ChatResponse,
    LlmConfig,
    ToolsUnsupportedError,
    VisionUnsupportedError,
    chat,
    generate,
    list_models,
)
from vera_app.markdown_drafts import current_draft_block
from vera_app.modes import Mode, load_modes, resolve_mode
from vera_app.search import search
from vera_app.types import Request, WriteEvent
from vera_doc import VeraDocument
from vera_ingest.viewer import get_chunk_regions

DEFAULT_RAG_INSTRUCTIONS = """You are VERA, a grounded document assistant.
Use only the cited evidence supplied in this prompt when answering.
Attach citation ids such as [C1] immediately after each claim they support.
Write citation ids as plain text — never inside backticks or other code formatting.
If the evidence is incomplete, say what is missing instead of guessing.
If cited evidence conflicts, describe the conflict and cite both sides.
Do not cite sources that are not present in the evidence list.
If tools are available, use them only to retrieve, verify, or inspect source-grounded information before answering."""


class AnswerStream:
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
        total += sum(
            1 for part in content if isinstance(part, dict) and part.get("type") == "image_url"
        )
    return total


def _clear_figure_context_flags(citations: list[dict[str, Any]]) -> None:
    for citation in citations:
        for figure in (citation.get("result") or {}).get("figures") or []:
            figure.pop("included_in_context", None)


def _source_name(request: Request, result: dict[str, Any]) -> str:
    """Document name shown to the model beside a passage.

    Attached files use the name the user dropped; library hits use the
    archive's source filename.
    """
    file = str(result.get("file") or "")
    if file:
        target = os.path.normcase(os.path.abspath(file))
        for row in attachment_rows(request):
            path = str(row.get("vera_path") or "")
            if path and os.path.normcase(os.path.abspath(path)) == target:
                return f"attached: {row.get('name') or os.path.basename(path)}"
    name = str(result.get("source_filename") or "")
    if name:
        return name
    return os.path.basename(file) if file else "document"


def _add_missing_regions(citations: list[dict[str, Any]], fallback_file: str = "") -> None:
    """Load highlight regions for cited passages that arrived without them.

    Full-text attachment chunks and passages reused from earlier evidence are
    cited from stored text, so they lack the regions a search hit carries.
    """
    by_file: dict[str, list[dict[str, Any]]] = {}
    for citation in citations:
        result = citation.get("result")
        if not isinstance(result, dict) or result.get("regions") or not result.get("chunk_id"):
            continue
        file = str(result.get("file") or fallback_file or "")
        if file:
            by_file.setdefault(file, []).append(result)
    for file, results in by_file.items():
        try:
            document = VeraDocument.open(file)
        except Exception:
            continue
        try:
            for result in results:
                try:
                    result["regions"] = get_chunk_regions(document, str(result["chunk_id"]))
                except Exception:
                    continue
        finally:
            document.close()


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


def _tool_choice(mode: Mode, turn: int, has_prior_evidence: bool, offering: bool) -> str:
    """``auto`` unless a mode's search_policy asks the model to call a tool."""
    if not offering:
        return "auto"
    policy = getattr(mode, "search_policy", "auto")
    if policy == "always":
        return "required"
    if policy == "first_turn" and turn == 0 and not has_prior_evidence:
        return "required"
    return "auto"


def _chat_turn(
    messages: list[dict[str, Any]],
    config: LlmConfig,
    *,
    tools: list[dict[str, Any]] | None,
    tool_choice: str,
    on_delta,
    cancel: CancellationToken | None,
) -> ChatResponse:
    """Call the model, retrying ``tool_choice=required`` as ``auto`` when rejected."""
    kwargs: dict[str, Any] = {"cancel": cancel} if cancel else {}
    try:
        return chat(
            messages,
            config,
            tools=tools,
            tool_choice=tool_choice,
            on_delta=on_delta,
            **kwargs,
        )
    except (CancelledError, VisionUnsupportedError, ToolsUnsupportedError):
        raise
    except Exception as exc:
        if tool_choice != "auto" and "tool_choice" in str(exc).lower():
            return chat(
                messages,
                config,
                tools=tools,
                tool_choice="auto",
                on_delta=on_delta,
                **kwargs,
            )
        raise


def _answered_from(request: Request, searches: list[dict[str, Any]]) -> str:
    if searches:
        return "search"
    attachments = request.get("file_attachments")
    if isinstance(attachments, list) and attachments:
        return "attachments"
    evidence = request.get("prior_evidence")
    if isinstance(evidence, list) and any(isinstance(item, dict) and item.get("text") for item in evidence):
        return "prior_evidence"
    return "none"


def _run_search_attachments(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    raw_ids = arguments.get("ids")
    ids = [str(item) for item in raw_ids if str(item).strip()] if isinstance(raw_ids, list) else None
    paths = searchable_paths(ctx.request, delivery_for(ctx.request), ids)
    if not paths:
        return {"error": "No searchable attached files match that request."}
    if ctx.search_tool is None:
        return {"error": "Search is not available."}
    return ctx.search_tool.run(arguments, paths_override=paths)


def _run_view_figure(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    if not ctx.vision_available:
        return {"error": "This model does not accept images."}
    if ctx.search_tool is None:
        return {"error": "Image viewing is not available."}
    asset_id = str(arguments.get("asset_id") or "").strip()
    if not asset_id:
        return {"error": "asset_id is required"}
    images = ctx.request.get("image_attachments")
    if isinstance(images, list):
        for image in images:
            if not isinstance(image, dict) or str(image.get("id") or "") != asset_id:
                continue
            url = str(image.get("data_url") or "")
            name = str(image.get("name") or asset_id)
            if ctx.search_tool.queue_image(url, f"Attached image {name}"):
                return {"ok": True, "name": name}
            return {"error": "Image budget exhausted."}
    file = str(arguments.get("file") or "").strip()
    if not file:
        for row in attachment_rows(ctx.request):
            candidate = str(row.get("vera_path") or "")
            if candidate:
                file = candidate
                break
    if not file:
        return {"error": "Figure file was not found."}
    from vera_app.search import figure_data

    rows = figure_data({"path": file, "asset_ids": [asset_id]})
    if not rows:
        return {"error": "Figure was not found."}
    url = str(rows[0].get("data_url") or "")
    caption = rows[0].get("caption") or asset_id
    if ctx.search_tool.queue_image(url, f"Figure {asset_id}: {caption}"):
        return {"ok": True, "asset_id": asset_id}
    return {"error": "Image budget exhausted."}


def _attachments_available(ctx: ToolContext) -> bool:
    return bool(searchable_paths(ctx.request, delivery_for(ctx.request)))


def _figures_available(ctx: ToolContext) -> bool:
    if not ctx.vision_available:
        return False
    images = ctx.request.get("image_attachments")
    if isinstance(images, list) and images:
        return True
    return bool(attachment_rows(ctx.request))


def _search_agent_tool(search_tool: SearchTool) -> AgentTool:
    return AgentTool(
        name="search",
        schema=SEARCH_TOOL,
        run=lambda arguments, _ctx: search_tool.run(arguments if isinstance(arguments, dict) else {}),
        max_calls=search_tool._mode.max_searches,
        available=lambda ctx: has_library_scope(ctx.request),
    )


WRITE_MARKDOWN_TOOL = {
    "type": "function",
    "function": {
        "name": "write_markdown",
        "description": (
            "Write a Markdown report when the user asks for a report, document, or file. "
            "Cite claims with [C#] or [A#] ids from the evidence. Keep the chat reply short."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {"type": "string"},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
}


def _run_write_markdown(arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    from vera_app.markdown_drafts import render_report, write_draft

    drafts_dir = str(ctx.request.get("drafts_dir") or "")
    if not drafts_dir:
        return {"error": "Drafts folder is not configured."}
    title = str(arguments.get("title") or "Report")
    content = str(arguments.get("content") or "")
    if not content.strip():
        return {"error": "content is required"}
    text, missing = render_report(title, content, ctx.citations)
    saved = write_draft(
        drafts_dir,
        str(ctx.request.get("session_id") or "session"),
        str(arguments.get("filename") or "report.md"),
        text,
    )
    saved["title"] = title
    if missing:
        saved["unresolved_citations"] = missing
    drafts = ctx.outputs.setdefault("drafts", [])
    if isinstance(drafts, list):
        drafts.append(saved)
    return saved


def _builtin_tools(search_tool: SearchTool) -> list[AgentTool]:
    mode = search_tool._mode
    return [
        _search_agent_tool(search_tool),
        AgentTool(
            name="search_attachments",
            schema=SEARCH_ATTACHMENTS_TOOL,
            run=_run_search_attachments,
            max_calls=mode.max_searches,
            available=_attachments_available,
        ),
        AgentTool(
            name="view_figure",
            schema=VIEW_FIGURE_TOOL,
            run=_run_view_figure,
            max_calls=max(1, mode.max_figure_images),
            available=_figures_available,
        ),
        AgentTool(
            name="write_markdown",
            schema=WRITE_MARKDOWN_TOOL,
            run=_run_write_markdown,
            max_calls=2,
        ),
    ]


def resolve_answer_mode(request: Request) -> Mode:
    return resolve_mode(
        str(request.get("mode_id") or "") or None,
        str(request.get("modes_dir") or "") or None,
    )


def list_modes(request: Request) -> dict[str, Any]:
    return {
        "modes": [
            mode.to_dict() for mode in load_modes(str(request.get("modes_dir") or "") or None)
        ]
    }


def list_llm_models(request: Request) -> dict[str, Any]:
    config = LlmConfig.from_request(request.get("llm"))
    models = list_models(config)
    return {"models": models}


def has_library_scope(request: Request) -> bool:
    """True when the request names a document, file list, or library folder."""
    paths = request.get("paths")
    if isinstance(paths, list) and any(str(path).strip() for path in paths):
        return True
    return bool(str(request.get("path") or "").strip())


class SearchTool:
    """Executes the model's `search` calls and accumulates citations."""

    # Relative score cutoffs as a fraction of the best hit in each search.
    # VERA's hybrid/keyword scores are RRF-based (not 0-1 cosine), so an absolute
    # threshold is unreliable; a per-search relative cutoff is mode-agnostic.
    _QUALITY_RATIOS = {"strict": 0.85, "balanced": 0.55, "permissive": 0.0}

    def __init__(
        self,
        request: Request,
        mode: Mode,
        write_event=None,
        label_registry: dict[str, str] | None = None,
        label_start: int = 0,
        cancel: CancellationToken | None = None,
        citations: CitationRegistry | None = None,
        paths_override: list[str] | None = None,
    ) -> None:
        self._request = request
        self._mode = mode
        self._paths_override = paths_override
        self._citations = citations or CitationRegistry()
        if label_registry:
            self._citations.seed_legacy_map(label_registry, label_start)
        # Recorded citations for this answer. Seeded prior labels stay out of
        # this list until a search retrieves them or the answer cites them.
        self.citations = self._citations.recorded
        self.searches: list[dict[str, Any]] = []
        self._write_event = write_event
        self._cancel = cancel
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
        return self._citations.label(result, record=True)

    def queue_image(self, data_url: str, note: str) -> bool:
        """Offer one image to the model if the per-answer image budget allows it."""
        if self._image_budget <= 0 or not data_url:
            return False
        self._pending_image_parts.append({"type": "text", "text": note})
        self._pending_image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
        self._image_budget -= 1
        return True

    def run(
        self,
        arguments: dict[str, Any],
        paths_override: list[str] | None = None,
    ) -> dict[str, Any]:
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
            self._write_event(
                {"event": "search_start", "query": query, "mode": search_mode, "top_k": top_k}
            )
        active_override = self._paths_override if paths_override is None else paths_override
        search_request = dict(self._request)
        if active_override is not None:
            search_request["paths"] = list(active_override)
            search_request.pop("path", None)
        results = search(
            {
                **search_request,
                "query": query,
                "mode": search_mode,
                "top_k": top_k,
                "context_chunks": max(0, min(3, int(context_chunks or 0))),
                "include_regions": True,
                "include_figures": include_figures,
                # Fetch actual image bytes (not just captions) so citations carry a
                # `data_url` the UI can render and so we can offer images to the LLM.
                "include_figure_data": include_figures,
            },
            cancel=self._cancel,
        )
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
            if chunk_id and self._citations.seen(result):
                skipped_cited += 1
                continue
            citation_id = self._register(result)
            passage: dict[str, Any] = {
                "citation": citation_id,
                "source": _source_name(self._request, result),
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
                        {
                            "type": "text",
                            "text": f"Figure for [{citation_id}] (p. {page}): {caption}",
                        }
                    )
                    self._pending_image_parts.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                    self._image_budget -= 1
            passages.append(passage)
        record_search: dict[str, Any] = {
            "query": query,
            "mode": search_mode,
            "top_k": top_k,
            "hits": len(passages),
        }
        if active_override is not None:
            record_search["scope"] = "attachments"
        self.searches.append(record_search)
        if self._write_event:
            self._write_event(
                {"event": "search_done", "query": query, "mode": search_mode, "hits": len(passages)}
            )
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
            response["note"] = (
                f"{skipped_cited} already-retrieved passage(s) omitted as duplicates."
            )
        return response


def _retrieval_payload(
    request: Request, mode: Mode, instructions: str, cancel: CancellationToken | None = None
) -> dict[str, Any]:
    """Non-agentic fallback: one search, then synthesize (or list passages)."""
    prompt = str(request.get("prompt", "")).strip()
    search_request = dict(request)
    if not has_library_scope(request):
        paths = [str(row.get("vera_path") or "") for row in attachment_rows(request)]
        paths = [path for path in paths if path]
        if not paths:
            results: list[dict[str, Any]] = []
        else:
            search_request["paths"] = paths
            search_request.pop("path", None)
            results = search(
                {
                    **search_request,
                    "query": prompt,
                    "mode": mode.search_mode,
                    "top_k": mode.top_k,
                    "context_chunks": mode.context_chunks,
                    "include_regions": True,
                    "include_figures": mode.include_figures,
                    "include_figure_data": mode.include_figures,
                },
                cancel=cancel,
            )
    else:
        results = search(
            {
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
            },
            cancel=cancel,
        )
    registry = CitationRegistry()
    scoped = scoped_single_file(request)
    if scoped:
        registry.fallback_file = scoped
    registry.seed_request(request)
    register_attachments(request, registry)
    citations = registry.recorded
    # Mirrors SearchTool.run()'s image-part queueing, bounded by the same
    # per-answer image budget.
    image_parts: list[dict[str, Any]] = []
    image_budget = mode.max_figure_images
    for result in results:
        citation_id = registry.label(result, record=True)
        page = result.get("page_start") or result.get("page_end") or "-"
        if mode.include_figures:
            for fig in result.get("figures") or []:
                data_url = fig.pop("data_url", None)
                if image_budget <= 0 or not data_url:
                    continue
                fig["included_in_context"] = True
                fig_page = fig.get("page_number") or page
                caption = fig.get("caption") or "no caption"
                image_parts.append(
                    {
                        "type": "text",
                        "text": f"Figure for [{citation_id}] (p. {fig_page}): {caption}",
                    }
                )
                image_parts.append({"type": "image_url", "image_url": {"url": data_url}})
                image_budget -= 1
    evidence = "\n".join(
        f"[{citation['id']}] ({_source_name(request, citation['result'])}) "
        f"{citation['result'].get('text', '')}"
        for citation in citations
    )
    llm_prompt = (
        f"Instructions:\n{instructions}\n\nUser question:\n{prompt}\n\nEvidence:\n{evidence}"
    )
    return {
        "prompt": prompt,
        "citations": citations,
        "instructions": instructions,
        "llm_prompt": llm_prompt,
        "image_parts": image_parts,
        "registry": registry,
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
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
        had_images = any(
            isinstance(part, dict) and part.get("type") == "image_url" for part in content
        )
        if had_images:
            note = "[Images omitted: this model does not support image input.]"
            text = f"{text}\n{note}" if text else note
        message["content"] = text


def answer(
    request: Request,
    write_event: WriteEvent | None = None,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    if cancel:
        cancel.raise_if_cancelled()
    prompt = str(request.get("prompt", "")).strip()
    if not prompt:
        raise ValueError("prompt is required")

    mode = resolve_answer_mode(request)
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
    registry = CitationRegistry()
    scoped = scoped_single_file(request)
    if scoped:
        registry.fallback_file = scoped
    registry.seed_request(request)
    tool = SearchTool(
        request,
        mode,
        write_event=record,
        cancel=cancel,
        citations=registry,
    )
    ctx = ToolContext(
        request=request,
        mode=mode,
        citations=registry,
        write_event=record,
        cancel=cancel,
        outputs={"searches": tool.searches},
        search_tool=tool,
    )
    table = ToolTable(allowlisted(_builtin_tools(tool), mode))
    if attachment_rows(request):
        instructions += (
            "\n\nThe user attached files. Use the attached text when it is included in full. "
            "Call search_attachments for files marked searchable. "
            "Call view_figure when you need to see a listed figure or an attached image. "
            "Attached-file passages carry [A#] ids; cite them exactly like [C#] ids."
        )
    instructions += (
        "\n\nWhen the user asks for a report, document, or file, call write_markdown "
        "and keep the chat reply to a short summary. Otherwise answer in the chat."
    )
    attachment_preamble, _delivery = build_attachment_prompt(request, registry)
    if searchable_paths(request, _delivery):
        tool.run(
            {"query": prompt, "top_k": mode.top_k, "include_figures": mode.include_figures},
            paths_override=searchable_paths(request, _delivery),
        )
    prior_block = evidence_block(request.get("prior_evidence"), evidence_token_budget(request))
    has_prior_evidence = bool(prior_block)
    # Images the user attached to this message (via the composer's attach button
    # or drag-and-drop) ride along in the initial user message, alongside any
    # figure images the agent surfaces later while searching.
    attachment_parts = _user_attachment_parts(request)
    draft_block = current_draft_block(request)
    question_parts = [part for part in (attachment_preamble, prior_block, draft_block, prompt) if part]
    question = "\n\n".join(question_parts)
    user_content: Any = question
    if attachment_parts:
        user_content = [{"type": "text", "text": question}, *attachment_parts]
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
        # One extra turn beyond the tool budgets lets the model write its final answer.
        for turn in range(table.max_turns()):
            if cancel:
                cancel.raise_if_cancelled()
            chunk_limited = tool.chunk_count >= mode.max_chunks
            offered = table.offered(ctx, force_answer=chunk_limited)
            force_answer = not offered
            offered_tools = table.schemas(offered)
            choice = _tool_choice(mode, turn, has_prior_evidence, bool(offered))
            answer_stream = AnswerStream(write_event)
            record(
                {
                    "event": "llm_request",
                    "turn": turn,
                    "model": config.model,
                    "tools": [item.schema_name() for item in offered],
                    "messages": _redact_messages_for_trace(messages),
                }
            )
            try:
                response = _chat_turn(
                    messages,
                    config,
                    tools=offered_tools,
                    tool_choice=choice,
                    on_delta=answer_stream.callback,
                    cancel=cancel,
                )
            except VisionUnsupportedError:
                # Neutralize every image-bearing message (user attachments and/or
                # figure images) and retry this turn once, text-only, without ever
                # offering images again this answer.
                answer_stream.abandon()
                answer_stream = AnswerStream(write_event)
                _strip_image_parts(messages)
                vision_available = False
                vision_fallback = True
                ctx.vision_available = False
                response = _chat_turn(
                    messages,
                    config,
                    tools=offered_tools,
                    tool_choice=choice,
                    on_delta=answer_stream.callback,
                    cancel=cancel,
                )
            if cancel:
                cancel.raise_if_cancelled()
            answer_stream.finish(response)
            last_response = response
            record(
                {
                    "event": "llm_response",
                    "turn": turn,
                    "model": response.model,
                    "content": response.content,
                    "tool_calls": [
                        {"id": call.id, "name": call.name, "arguments": call.arguments}
                        for call in response.tool_calls
                    ],
                    "usage": response.usage,
                }
            )
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
                output = table.dispatch(
                    call.name,
                    call.arguments if isinstance(call.arguments, dict) else {},
                    ctx,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(output),
                    }
                )
                record(
                    {
                        "event": "tool_call",
                        "turn": turn,
                        "name": call.name,
                        "arguments": call.arguments,
                        "output": output,
                    }
                )
            # If any of this turn's searches surfaced figures within the image
            # budget, offer them to the model as a follow-up multimodal message so
            # it can actually see the images (not just their captions).
            if vision_available:
                image_parts = tool.take_pending_image_parts()
                if image_parts:
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Reference images for the figures cited above:",
                                },
                                *image_parts,
                            ],
                        }
                    )
            print(
                f"[vera-answer]   -> appended tool results, messages now {len(messages)}, "
                f"total citations: {tool.chunk_count}",
                file=sys.stderr,
                flush=True,
            )
    except ToolsUnsupportedError:
        # Provider can't do tool-calling: fall back to one-shot retrieve-then-answer.
        answer_stream.abandon()
        fallback = _retrieval_payload(request, mode, instructions, cancel=cancel)
        fallback_prompt = fallback["llm_prompt"]
        prefix = "\n\n".join(part for part in (attachment_preamble, prior_block) if part)
        if prefix:
            fallback_prompt = f"{prefix}\n\n{fallback_prompt}"
        fallback_user_content: Any = fallback_prompt
        if attachment_parts:
            fallback_user_content = [
                {"type": "text", "text": fallback["llm_prompt"]},
                *attachment_parts,
            ]
        fallback_messages: list[dict[str, Any]] = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": fallback_user_content},
        ]
        if fallback["image_parts"]:
            fallback_messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Reference images for the figures cited above:"},
                        *fallback["image_parts"],
                    ],
                }
            )
        record(
            {
                "event": "llm_request",
                "turn": 0,
                "model": config.model,
                "tools": [],
                "messages": _redact_messages_for_trace(fallback_messages),
            }
        )
        fallback_stream = AnswerStream(write_event)
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
            fallback_stream = AnswerStream(write_event)
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
        record(
            {
                "event": "llm_response",
                "turn": 0,
                "model": llm_result.model,
                "content": llm_result.answer,
                "tool_calls": [],
                "usage": llm_result.usage,
            }
        )
        images_sent = _count_image_parts(fallback_messages)
        if images_sent == 0:
            _clear_figure_context_flags(fallback["citations"])
        unresolved = fallback["registry"].resolve_answer(llm_result.answer)
        if unresolved:
            record({"event": "citation_resolve", "unresolved": unresolved})
        _add_missing_regions(fallback["citations"], scoped or "")
        return {
            "prompt": prompt,
            "answer": llm_result.answer,
            "citations": fallback["citations"],
            "instructions": instructions,
            "mode": mode.id,
            "mode_label": mode.label,
            "answer_mode": "retrieval",
            "answered_from": "search" if fallback["citations"] else _answered_from(request, []),
            "searches": [],
            "trace": trace,
            "images_sent": images_sent,
            "vision_fallback": vision_fallback,
            "llm": {
                "provider": llm_result.provider,
                "model": llm_result.model,
                "usage": llm_result.usage,
            },
        }

    answer_text = last_response.content if last_response else ""
    if not answer_text and tool.citations:
        # The model returned empty content on the final turn (common when the tool
        # budget runs out and tools are dropped from the payload, leaving some models
        # momentarily confused).  Send a short nudge to get the synthesis.
        nudge_stream = AnswerStream(write_event)
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
            record(
                {
                    "event": "llm_request",
                    "turn": mode.max_searches + 1,
                    "model": config.model,
                    "tools": [],
                    "messages": _redact_messages_for_trace(nudge_messages),
                }
            )
            nudge = chat(
                nudge_messages,
                config,
                tools=None,
                tool_choice="auto",
                on_delta=nudge_stream.callback,
                **({"cancel": cancel} if cancel else {}),
            )
            nudge_stream.finish(nudge)
            record(
                {
                    "event": "llm_response",
                    "turn": mode.max_searches + 1,
                    "model": nudge.model,
                    "content": nudge.content,
                    "tool_calls": [],
                    "usage": nudge.usage,
                }
            )
            answer_text = nudge.content
            if nudge.model:
                last_response = nudge
        except CancelledError:
            raise
        except Exception:
            nudge_stream.abandon()
            pass
    if not answer_text:
        answer_text = "I could not produce an answer from the selected VERA source."
    unresolved = registry.resolve_answer(answer_text)
    if unresolved:
        record({"event": "citation_resolve", "unresolved": unresolved})
    _add_missing_regions(tool.citations, scoped or "")
    images_sent = _count_image_parts(messages)
    if images_sent == 0:
        _clear_figure_context_flags(tool.citations)
    if attachment_rows(request):
        ctx.outputs["attachment_usage"] = attachment_usage(
            attachment_rows(request),
            _delivery,
            tool.searches,
            tool.citations,
        )
    extra_outputs = {key: value for key, value in ctx.outputs.items() if key != "searches"}
    return {
        "prompt": prompt,
        "answer": answer_text,
        "citations": tool.citations,
        "instructions": instructions,
        "mode": mode.id,
        "mode_label": mode.label,
        "answer_mode": "agent",
        "answered_from": _answered_from(request, tool.searches),
        "searches": tool.searches,
        **extra_outputs,
        "trace": trace,
        "images_sent": images_sent,
        "vision_fallback": vision_fallback,
        "llm": {
            "provider": "openai_compatible",
            "model": last_response.model if last_response else config.model,
            "usage": last_response.usage if last_response else None,
        },
    }
