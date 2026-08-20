"""Ask SearchTool quality filtering, citation labels, and stream sanitization."""

from __future__ import annotations

from vera_app.chat import (
    AnswerStream,
    SearchTool,
    _prior_citation_labels,
    _user_attachment_parts,
)
from vera_app.llm import ChatResponse
from vera_app.modes import Mode


def _mode(**overrides) -> Mode:
    values = dict(
        id="ask",
        label="Ask",
        search_mode="hybrid",
        top_k=8,
        context_chunks=1,
        include_figures=False,
        max_searches=6,
        max_chunks=20,
        max_figure_images=4,
    )
    values.update(overrides)
    return Mode(**values)


def _hits(*scores: tuple[str, float, str]):
    return [
        {
            "chunk_id": chunk_id,
            "score": score,
            "text": text,
            "page_start": index + 1,
            "heading_path": "Chapter 1",
        }
        for index, (chunk_id, score, text) in enumerate(scores)
    ]


def test_search_tool_requires_query(monkeypatch):
    monkeypatch.setattr("vera_app.chat.search", lambda *args, **kwargs: _hits())
    tool = SearchTool({"path": "manual.vera"}, _mode())
    assert tool.run({}) == {"error": "query is required"}
    assert tool.run({"query": "   "})["error"] == "query is required"


def test_search_tool_strict_quality_drops_weak_hits(monkeypatch):
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda *args, **kwargs: _hits(
            ("strong", 1.0, "best match"),
            ("weak", 0.50, "far weaker"),
        ),
    )
    tool = SearchTool({"path": "manual.vera"}, _mode())
    result = tool.run({"query": "detention", "quality": "strict"})
    assert [item["citation"] for item in result["passages"]] == ["C1"]
    assert result["passages"][0]["text"] == "best match"


def test_search_tool_permissive_keeps_weak_hits(monkeypatch):
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda *args, **kwargs: _hits(
            ("strong", 1.0, "best match"),
            ("weak", 0.10, "far weaker"),
        ),
    )
    tool = SearchTool({"path": "manual.vera"}, _mode())
    result = tool.run({"query": "detention", "quality": "permissive"})
    assert [item["citation"] for item in result["passages"]] == ["C1", "C2"]


def test_search_tool_unknown_quality_and_mode_fall_back(monkeypatch):
    seen = {}

    def fake_search(request, cancel=None):
        seen["mode"] = request["mode"]
        return _hits(("strong", 1.0, "best"), ("weak", 0.50, "weaker"))

    monkeypatch.setattr("vera_app.chat.search", fake_search)
    tool = SearchTool({"path": "manual.vera"}, _mode(search_mode="keyword"))
    result = tool.run({"query": "detention", "mode": "fuzzy", "quality": "mystery"})
    assert seen["mode"] == "keyword"
    # balanced cutoff is 0.55, so 0.50 is dropped.
    assert [item["citation"] for item in result["passages"]] == ["C1"]


def test_search_tool_reuses_prior_citation_ids(monkeypatch):
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda *args, **kwargs: _hits(
            ("old", 1.0, "previously cited"),
            ("new", 0.9, "fresh passage"),
        ),
    )
    tool = SearchTool(
        {"path": "manual.vera"},
        _mode(),
        label_registry={"old": "C7"},
        label_start=7,
    )
    result = tool.run({"query": "detention", "quality": "permissive"})
    assert [item["citation"] for item in result["passages"]] == ["C7", "C8"]
    assert tool.citations[0]["id"] == "C7"
    assert tool.citations[1]["id"] == "C8"


def test_search_tool_skips_already_retrieved_chunks(monkeypatch):
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda *args, **kwargs: _hits(("same", 1.0, "repeat")),
    )
    tool = SearchTool({"path": "manual.vera"}, _mode())
    first = tool.run({"query": "first"})
    second = tool.run({"query": "second"})
    assert first["passages"][0]["citation"] == "C1"
    assert second["passages"] == []
    assert "already retrieved" in second["note"]


def test_search_tool_reports_chunk_budget_exhausted(monkeypatch):
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda *args, **kwargs: _hits(("a", 1.0, "one")),
    )
    tool = SearchTool({"path": "manual.vera"}, _mode(max_chunks=1))
    first = tool.run({"query": "first"})
    assert first["passages"][0]["citation"] == "C1"
    result = tool.run({"query": "second"})
    assert "Chunk budget exhausted" in result["error"]


def test_search_tool_caps_top_k_to_remaining_budget(monkeypatch):
    seen = {}

    def fake_search(request, cancel=None):
        seen["top_k"] = request["top_k"]
        return _hits(("a", 1.0, "one"))

    monkeypatch.setattr("vera_app.chat.search", fake_search)
    tool = SearchTool({"path": "manual.vera"}, _mode(max_chunks=2, top_k=8))
    tool.run({"query": "first", "top_k": 20})
    assert seen["top_k"] == 2


def test_prior_citation_labels_skip_malformed_and_keep_first_id():
    registry, max_index = _prior_citation_labels(
        {
            "prior_citations": [
                "skip-me",
                {"id": "", "chunk_id": "a"},
                {"id": "C9", "chunk_id": "old"},
                {"id": "C2", "chunk_id": "old"},
                {"id": "note", "chunk_id": "other"},
            ]
        }
    )
    assert registry == {"old": "C9", "other": "note"}
    assert max_index == 9


def test_user_attachment_parts_ignore_invalid_entries():
    parts = _user_attachment_parts(
        {
            "attachments": [
                "nope",
                {"caption": "missing url"},
                {"data_url": "data:image/png;base64,abc"},
            ]
        }
    )
    assert parts == [{"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}}]


def test_answer_stream_holds_then_blocks_functions_markup():
    events: list[dict] = []
    stream = AnswerStream(events.append)
    stream.feed("Hello <func")
    assert events == [{"event": "answer_delta", "text": "Hello "}]
    stream.feed("tions.search>")
    assert events == [{"event": "answer_delta", "text": "Hello "}]
    stream.feed(" leftover")
    assert events == [{"event": "answer_delta", "text": "Hello "}]


def test_answer_stream_finish_replaces_partial_visible_text():
    events: list[dict] = []
    stream = AnswerStream(events.append)
    stream.feed("Draft ")
    stream.finish(
        ChatResponse(
            content="Final answer [C1]",
            tool_calls=[],
            message={"role": "assistant", "content": "Final answer [C1]"},
            model="test-model",
            usage=None,
        )
    )
    assert events[-2:] == [
        {"event": "answer_reset"},
        {"event": "answer_delta", "text": "Final answer [C1]"},
    ]
