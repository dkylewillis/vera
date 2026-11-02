"""Attachment delivery, conversion cache, and prompt blocks."""

from __future__ import annotations

from vera_app.agent_tools import ToolContext, ToolTable
from vera_app.chat import (
    SearchTool,
    _add_missing_regions,
    _answered_from,
    _builtin_tools,
    _run_view_figure,
    has_library_scope,
)
from vera_app.chat_attachments import (
    build_attachment_prompt,
    delivery_for,
    full_text_block,
    handle_chat_attachment_prepare,
    manifest_text,
    plan_delivery,
    register_attachments,
    searchable_paths,
)
from vera_app.citations import CitationRegistry, attachment_token_cap
from vera_app.modes import Mode
from vera_doc import VeraDocument


def test_plan_delivery_stops_after_the_cap() -> None:
    rows = [
        {"id": "a", "token_estimate": 100},
        {"id": "b", "token_estimate": 50},
        {"id": "c", "token_estimate": 10},
    ]
    assert plan_delivery(rows, 120) == {"a": "full", "b": "searchable", "c": "searchable"}


def test_plan_delivery_keeps_a_small_first_file() -> None:
    rows = [
        {"id": "a", "token_estimate": 10},
        {"id": "b", "token_estimate": 10},
    ]
    assert plan_delivery(rows, 25) == {"a": "full", "b": "full"}


def test_local_attachment_cap_is_smaller_than_cloud() -> None:
    local = attachment_token_cap({"llm": {"provider": "ollama"}})
    cloud = attachment_token_cap({"llm": {"provider": "openai"}})
    assert local < cloud
    assert cloud == 40_000


def test_full_text_block_labels_without_recording() -> None:
    registry = CitationRegistry()
    text = full_text_block(
        {"id": "file_1", "name": "notes.md", "vera_path": "notes.vera"},
        [
            {
                "chunk_id": "chunk_0001",
                "text": "Pond volume is fixed.",
                "metadata": {"page_start": 2, "heading_path": "Design"},
            }
        ],
        registry,
        [{"asset_id": "image_1", "page_number": 2, "caption": "Pond"}],
    )
    assert "[C1]" in text
    assert "asset_id=image_1" in text
    assert registry.recorded == []
    assert registry.resolve_answer("See [C1].") == []
    assert registry.recorded[0]["result"]["file"] == "notes.vera"


def _chunks(*texts: str) -> list[dict]:
    return [
        {"chunk_id": f"chunk_{index:04d}", "text": text, "metadata": {"page_start": 1}}
        for index, text in enumerate(texts, start=1)
    ]


def test_attached_chunks_get_fixed_a_numbers_beside_search_results(monkeypatch) -> None:
    files = {
        "first.vera": _chunks("one", "two", "three"),
        "second.vera": _chunks("four", "five"),
    }
    monkeypatch.setattr("vera_app.chat_attachments.read_chunks", lambda path: files[path])
    request = {
        "file_attachments": [
            {"id": "a", "name": "first.md", "vera_path": "first.vera", "chunk_count": 3, "label_start": 1, "token_estimate": 3},
            {"id": "b", "name": "second.md", "vera_path": "second.vera", "chunk_count": 2, "label_start": 4, "token_estimate": 2},
        ],
    }
    for _turn in range(2):
        registry = CitationRegistry()
        text, _delivery = build_attachment_prompt(request, registry)
        assert "[A1] (p. 1) one" in text
        assert "[A5] (p. 1) five" in text
        assert registry.label({"chunk_id": "chunk_0001", "file": "library.vera"}) == "C1"
        assert registry.label({"chunk_id": "chunk_0002", "file": "second.vera"}) == "A5"
    fresh = CitationRegistry()
    register_attachments(request, fresh)
    assert fresh.resolve_answer("Volume [A2] and [A4].") == []
    assert [entry["id"] for entry in fresh.recorded] == ["A2", "A4"]
    assert fresh.recorded[1]["result"]["file"] == "second.vera"


def test_full_text_block_drops_the_repeated_overlap() -> None:
    registry = CitationRegistry()
    text = full_text_block(
        {"id": "a", "name": "notes.md", "vera_path": "notes.vera"},
        _chunks("alpha beta gamma delta", "gamma delta epsilon zeta", "unrelated start"),
        registry,
    )
    assert "[C2] (p. 1) epsilon zeta" in text
    assert "[C3] (p. 1) unrelated start" in text


def test_cited_full_text_chunk_gets_highlight_regions(tmp_path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Pond\n\nThe pond holds 1.2 acre-feet.\n", encoding="utf-8")
    prepared = handle_chat_attachment_prepare(
        {"input": str(source), "attachments_dir": str(tmp_path / "cache"), "model": "hashing"}
    )
    request = {
        "file_attachments": [
            {"id": "a", "name": "notes.md", "label_start": 1, "token_estimate": 20, **prepared},
        ],
    }
    registry = CitationRegistry()
    build_attachment_prompt(request, registry)
    assert registry.resolve_answer("It holds 1.2 acre-feet. [A1]") == []
    assert "regions" not in registry.recorded[0]["result"]
    _add_missing_regions(registry.recorded)
    assert registry.recorded[0]["result"]["regions"]


def test_prepared_archive_keeps_the_original(tmp_path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("The pond holds 1.2 acre-feet.\n", encoding="utf-8")
    prepared = handle_chat_attachment_prepare(
        {"input": str(source), "attachments_dir": str(tmp_path / "cache"), "model": "hashing"}
    )
    document = VeraDocument.open(prepared["vera_path"])
    try:
        assert document.metadata.get("source_attachment_id")
    finally:
        document.close()
    assert not list(tmp_path.glob(".*.md"))


def test_manifest_names_searchable_files() -> None:
    text = manifest_text(
        [{"id": "b", "name": "spec.pdf", "page_count": 12, "token_estimate": 9000, "outline": ["Scope"]}],
        {"b": "searchable"},
    )
    assert "spec.pdf" in text
    assert "search_attachments" in text
    assert "Scope" in text


def test_prepare_converts_markdown_and_reuses_the_cache(tmp_path) -> None:
    source = tmp_path / "notes.md"
    source.write_text("# Pond\n\nThe pond holds 1.2 acre-feet.\n", encoding="utf-8")
    cache = tmp_path / "cache"
    request = {"input": str(source), "attachments_dir": str(cache), "model": "hashing"}
    first = handle_chat_attachment_prepare(request)
    second = handle_chat_attachment_prepare(request)
    assert first["vera_path"] == second["vera_path"]
    assert first["chunk_count"] >= 1
    assert first["vera_path"].endswith(".vera")
    assert "notes" in first["vera_path"]


def test_empty_path_is_not_a_library() -> None:
    assert has_library_scope({"path": ""}) is False
    assert has_library_scope({"path": "manual.vera"}) is True
    assert has_library_scope({"paths": ["one.vera"]}) is True


def test_search_attachments_scope_follows_delivery_and_ids() -> None:
    request = {
        "llm": {"provider": "ollama"},
        "file_attachments": [
            {"id": "full", "vera_path": "full.vera", "token_estimate": 10},
            {"id": "big", "vera_path": "big.vera", "token_estimate": 100_000},
            {"id": "other", "vera_path": "other.vera", "token_estimate": 100_000},
        ],
    }
    delivery = delivery_for(request)
    assert delivery["full"] == "full"
    assert searchable_paths(request, delivery) == ["big.vera", "other.vera"]
    assert searchable_paths(request, delivery, ["other"]) == ["other.vera"]
    resent = {**request, "full_attachment_ids": ["full"]}
    assert delivery_for(resent)["big"] == "searchable"
    dropped = {**request, "full_attachment_ids": []}
    assert delivery_for(dropped)["full"] == "searchable"


def test_answered_from_prefers_search_then_attachments_then_evidence() -> None:
    assert _answered_from({}, [{"query": "pond"}]) == "search"
    assert _answered_from({"file_attachments": [{"id": "a"}]}, []) == "attachments"
    assert _answered_from({"prior_evidence": [{"text": "pond"}]}, []) == "prior_evidence"
    assert _answered_from({}, []) == "none"


def test_view_figure_queues_a_session_image_and_hides_when_vision_is_off() -> None:
    mode = Mode(id="ask", label="Ask", max_searches=1, max_figure_images=1)
    request = {
        "path": "manual.vera",
        "image_attachments": [{"id": "photo", "name": "pond.png", "data_url": "data:image/png;base64,aa"}],
    }
    search_tool = SearchTool(request, mode)
    ctx = ToolContext(
        request=request,
        mode=mode,
        citations=CitationRegistry(),
        search_tool=search_tool,
    )
    table = ToolTable(_builtin_tools(search_tool))
    assert "view_figure" in [tool.name for tool in table.offered(ctx)]
    assert _run_view_figure({"asset_id": "photo"}, ctx)["ok"] is True
    assert search_tool.take_pending_image_parts()[1]["image_url"]["url"].startswith("data:image")
    assert _run_view_figure({"asset_id": "photo"}, ctx)["error"] == "Image budget exhausted."
    ctx.vision_available = False
    assert "view_figure" not in [tool.name for tool in table.offered(ctx)]
    writer = next(tool for tool in table.tools if tool.name == "write_markdown")
    assert writer.max_calls == 2
