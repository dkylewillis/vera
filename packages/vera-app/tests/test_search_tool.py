"""SearchTool quality cutoffs, query validation, and citation budget."""

from __future__ import annotations

from vera_app.chat import SearchTool
from vera_app.modes import Mode


def _hits(*scores: tuple[str, float]) -> list[dict]:
    return [
        {
            "chunk_id": chunk_id,
            "score": score,
            "text": f"passage {chunk_id}",
            "page_start": index + 1,
            "page_end": index + 1,
        }
        for index, (chunk_id, score) in enumerate(scores)
    ]


def test_search_tool_requires_a_nonempty_query() -> None:
    tool = SearchTool({}, Mode(id="ask", label="Ask"))
    assert tool.run({"query": "   "}) == {"error": "query is required"}


def test_search_tool_strict_quality_drops_weak_hits(monkeypatch) -> None:
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda request, cancel=None: _hits(("strong", 1.0), ("weak", 0.50)),
    )
    tool = SearchTool({}, Mode(id="ask", label="Ask"))
    result = tool.run({"query": "detention", "quality": "strict"})
    assert [passage["citation"] for passage in result["passages"]] == ["C1"]
    assert result["passages"][0]["text"] == "passage strong"


def test_search_tool_unknown_quality_uses_balanced_cutoff(monkeypatch) -> None:
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda request, cancel=None: _hits(("strong", 1.0), ("mid", 0.50)),
    )
    tool = SearchTool({}, Mode(id="ask", label="Ask"))
    result = tool.run({"query": "detention", "quality": "not-a-tier"})
    assert [passage["text"] for passage in result["passages"]] == ["passage strong"]


def test_search_tool_permissive_keeps_weak_hits(monkeypatch) -> None:
    monkeypatch.setattr(
        "vera_app.chat.search",
        lambda request, cancel=None: _hits(("strong", 1.0), ("weak", 0.10)),
    )
    tool = SearchTool({}, Mode(id="ask", label="Ask"))
    result = tool.run({"query": "detention", "quality": "permissive"})
    assert [passage["citation"] for passage in result["passages"]] == ["C1", "C2"]


def test_search_tool_exhausted_budget_and_duplicate_hits(monkeypatch) -> None:
    def fake_search(request, cancel=None):
        hits = _hits(("a", 1.0), ("b", 0.9))
        return hits[: int(request.get("top_k", 10))]

    monkeypatch.setattr("vera_app.chat.search", fake_search)
    tool = SearchTool({}, Mode(id="ask", label="Ask", max_chunks=1))
    first = tool.run({"query": "detention", "quality": "permissive"})
    assert len(first["passages"]) == 1
    assert first["passages"][0]["citation"] == "C1"

    exhausted = tool.run({"query": "again"})
    assert exhausted["error"].startswith("Chunk budget exhausted")

    tool_dup = SearchTool({}, Mode(id="ask", label="Ask", max_chunks=4))
    tool_dup.run({"query": "first", "quality": "permissive"})
    again = tool_dup.run({"query": "second", "quality": "permissive"})
    assert again["passages"] == []
    assert "already retrieved" in again["note"]
