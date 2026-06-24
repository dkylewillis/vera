from __future__ import annotations

import base64
import copy
import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from vera import VeraDocument, convert
from vera.corpus import VeraCorpus
from vera_app.llm import (
    ChatResponse,
    LlmConfig,
    ToolsUnsupportedError,
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
If the evidence is incomplete, say what is missing instead of guessing.
If cited evidence conflicts, describe the conflict and cite both sides.
Do not cite sources that are not present in the evidence list.
If tools are available, use them only to retrieve, verify, or inspect source-grounded information before answering."""


def _open_document(path: str) -> VeraDocument:
    return VeraDocument.open(path)


def _figure_payload(figure: dict[str, Any]) -> dict[str, Any]:
    data = figure.pop("data", None)
    if data is not None:
        mime_type = figure.get("mime_type") or "application/octet-stream"
        figure["data_url"] = f"data:{mime_type};base64,{base64.b64encode(data).decode('ascii')}"
    return figure


def _inspect(request: Request) -> dict[str, Any]:
    path = str(request["path"])
    if Path(path).is_dir():
        corpus = VeraCorpus.open(path)
        try:
            return corpus.inspect()
        finally:
            corpus.close()
    doc = _open_document(path)
    try:
        return doc.inspect()
    finally:
        doc.close()


def _validate(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        return doc.validate()
    finally:
        doc.close()


def _search(request: Request) -> list[dict[str, Any]]:
    path = str(request["path"])
    target = VeraCorpus.open(path) if Path(path).is_dir() else _open_document(path)
    try:
        results = target.search(
            str(request.get("query", "")),
            mode=str(request.get("mode", "hybrid")),
            top_k=int(request.get("top_k", 10)),
            context_chunks=int(request.get("context_chunks", 0)),
        )
        include_regions = bool(request.get("include_regions", False))
        include_figures = bool(request.get("include_figures", False))
        include_figure_data = bool(request.get("include_figure_data", False))
        payload: list[dict[str, Any]] = []
        for result in results:
            entry = result.as_dict()
            if include_regions:
                entry["regions"] = target.regions_for(result)
            if include_figures:
                entry["figures"] = [_figure_payload(figure) for figure in target.figures_for(result, include_data=include_figure_data)]
            payload.append(entry)
        return payload
    finally:
        target.close()


def _compact_text(text: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


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


class _SearchTool:
    """Executes the model's `search` calls and accumulates citations."""

    # Relative score cutoffs as a fraction of the best hit in each search.
    # VERA's hybrid/keyword scores are RRF-based (not 0-1 cosine), so an absolute
    # threshold is unreliable; a per-search relative cutoff is mode-agnostic.
    _QUALITY_RATIOS = {"strict": 0.85, "balanced": 0.55, "permissive": 0.0}

    def __init__(self, request: Request, mode: Mode, write_event=None) -> None:
        self._request = request
        self._mode = mode
        self._by_chunk: dict[str, dict[str, Any]] = {}
        self.citations: list[dict[str, Any]] = []
        self.searches: list[dict[str, Any]] = []
        self._write_event = write_event

    @property
    def chunk_count(self) -> int:
        return len(self.citations)

    def _register(self, result: dict[str, Any]) -> str:
        chunk_id = str(result.get("chunk_id") or f"chunk_{len(self._by_chunk)}")
        existing = self._by_chunk.get(chunk_id)
        if existing is not None:
            return str(existing["id"])
        citation_id = f"C{len(self.citations) + 1}"
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
    })
    citations = []
    for index, result in enumerate(results, start=1):
        citation_id = f"C{index}"
        page = result.get("page_start") or result.get("page_end") or "-"
        citations.append({
            "id": citation_id,
            "label": f"[{citation_id}] p. {page}",
            "result": result,
        })
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
    }


def _answer(request: Request, write_event=None) -> dict[str, Any]:
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

    tool = _SearchTool(request, mode, write_event=write_event)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": instructions},
        *history,
        {"role": "user", "content": prompt},
    ]

    # Collect a structured trace of every LLM request/response and tool call so the
    # UI can show exactly what was sent to and received from the model.
    trace: list[dict[str, Any]] = []

    def record(entry: dict[str, Any]) -> None:
        trace.append(entry)
        if write_event:
            write_event(entry)

    last_response: ChatResponse | None = None
    try:
        # One extra turn beyond the search budget lets the model write its final answer.
        for turn in range(mode.max_searches + 1):
            force_answer = turn >= mode.max_searches or tool.chunk_count >= mode.max_chunks
            offered_tools = None if force_answer else [SEARCH_TOOL]
            record({
                "event": "llm_request",
                "turn": turn,
                "model": config.model,
                "tools": [t["function"]["name"] for t in (offered_tools or [])],
                "messages": copy.deepcopy(messages),
            })
            response = chat(
                messages,
                config,
                tools=offered_tools,
                tool_choice="auto",
            )
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
            print(
                f"[vera-answer]   -> appended tool results, messages now {len(messages)}, "
                f"total citations: {tool.chunk_count}",
                file=sys.stderr,
                flush=True,
            )
    except ToolsUnsupportedError:
        # Provider can't do tool-calling: fall back to one-shot retrieve-then-answer.
        fallback = _retrieval_payload(request, mode, instructions)
        fallback_messages = [
            {"role": "system", "content": instructions},
            {"role": "user", "content": fallback["llm_prompt"]},
        ]
        record({
            "event": "llm_request",
            "turn": 0,
            "model": config.model,
            "tools": [],
            "messages": copy.deepcopy(fallback_messages),
        })
        llm_result = generate(fallback_messages, config)
        record({
            "event": "llm_response",
            "turn": 0,
            "model": llm_result.model,
            "content": llm_result.answer,
            "tool_calls": [],
            "usage": llm_result.usage,
        })
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
            "llm": {"provider": llm_result.provider, "model": llm_result.model, "usage": llm_result.usage},
        }

    answer = last_response.content if last_response else ""
    if not answer and tool.citations:
        # The model returned empty content on the final turn (common when the tool
        # budget runs out and tools are dropped from the payload, leaving some models
        # momentarily confused).  Send a short nudge to get the synthesis.
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
                "messages": copy.deepcopy(nudge_messages),
            })
            nudge = chat(
                nudge_messages,
                config,
                tools=None,
                tool_choice="auto",
            )
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
        except Exception:
            pass
    if not answer:
        answer = "I could not produce an answer from the selected VERA source."
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
        "llm": {
            "provider": "openai_compatible",
            "model": last_response.model if last_response else config.model,
            "usage": last_response.usage if last_response else None,
        },
    }



def _convert(request: Request) -> dict[str, str]:
    output = convert(
        str(request["input"]),
        str(request["output"]),
        model=str(request.get("model", "hashing")),
        parser=str(request.get("parser", "pymupdf")),
        chunk_size=int(request.get("chunk_size", 500)),
        overlap=int(request.get("overlap", 75)),
        store_original=bool(request.get("store_original", True)),
    )
    return {"output": output}


def _export(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        output = doc.export_source_document(str(request["output"]) if request.get("output") else None)
        source = doc.get_source_document()
        return {
            "output": output,
            "filename": source.filename,
            "mime_type": source.mime_type,
            "hash": source.hash,
        }
    finally:
        doc.close()


def _source(request: Request) -> dict[str, Any]:
    doc = _open_document(str(request["path"]))
    try:
        source = doc.get_source_document()
        mime_type = source.mime_type or "application/octet-stream"
        return {
            "filename": source.filename,
            "mime_type": mime_type,
            "hash": source.hash,
            "size": len(source.data),
            "data_url": f"data:{mime_type};base64,{base64.b64encode(source.data).decode('ascii')}",
        }
    finally:
        doc.close()


def _page(request: Request) -> dict[str, Any] | None:
    doc = _open_document(str(request["path"]))
    try:
        return doc.get_page(int(request["page_number"]))
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
    "search": _search,
    "answer": _answer,
    "convert": _convert,
    "export": _export,
    "source": _source,
    "page": _page,
    "list_models": _list_models,
    "list_modes": _list_modes,
}


def handle(request: Request) -> Response:
    request_id = request.get("id")
    try:
        action = str(request.get("action", ""))
        if action not in HANDLERS:
            raise ValueError(f"Unknown action: {action}")
        if action == "answer":
            def _emit(data: dict[str, Any]) -> None:
                print(json.dumps({**data, "id": request_id}), flush=True)
            result = _answer(request, write_event=_emit)
        else:
            result = HANDLERS[action](request)
        return {"id": request_id, "ok": True, "result": result}
    except Exception as exc:
        return {
            "id": request_id,
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: Response = {"id": None, "ok": False, "error": str(exc)}
        else:
            response = handle(request)
        print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
