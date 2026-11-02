"""Citation keys, evidence budgeting, and answer-time label resolution."""

from __future__ import annotations

from vera_app.citations import CitationRegistry, evidence_block, evidence_token_budget


def test_citation_keys_do_not_collide_across_files() -> None:
    registry = CitationRegistry()
    first = registry.label({"chunk_id": "chunk_0001", "file": r"C:\a.vera", "page_start": 1, "text": "a"})
    second = registry.label({"chunk_id": "chunk_0001", "file": r"C:\b.vera", "page_start": 2, "text": "b"})
    assert first == "C1"
    assert second == "C2"
    assert registry.lookup("C1")["result"]["file"].endswith("a.vera")
    assert registry.lookup("C2")["result"]["file"].endswith("b.vera")


def test_legacy_chunk_id_prior_citation_is_reused() -> None:
    registry = CitationRegistry()
    registry.seed_request({"prior_citations": [{"id": "C4", "chunk_id": "chunk_0001"}]})
    reused = registry.label({"chunk_id": "chunk_0001", "page_start": 3, "text": "again"})
    assert reused == "C4"
    fresh = registry.label({"chunk_id": "chunk_0002", "page_start": 4, "text": "new"})
    assert fresh == "C5"


def test_file_scoped_prior_citation_does_not_match_a_different_file() -> None:
    registry = CitationRegistry()
    registry.seed_request(
        {"prior_citations": [{"id": "C1", "chunk_id": "chunk_0001", "file": r"C:\a.vera"}]}
    )
    other = registry.label({"chunk_id": "chunk_0001", "file": r"C:\b.vera", "text": "other"})
    same = registry.label({"chunk_id": "chunk_0001", "file": r"C:\a.vera", "text": "same"})
    assert same == "C1"
    assert other == "C2"


def test_resolve_answer_records_seeded_evidence_only_when_cited() -> None:
    registry = CitationRegistry()
    registry.seed_request(
        {
            "prior_evidence": [
                {
                    "id": "C2",
                    "chunk_id": "chunk_0002",
                    "file": "manual.vera",
                    "text": "Pond volume is 1.2 acre-feet.",
                    "page_start": 10,
                    "source_filename": "manual.pdf",
                }
            ]
        }
    )
    assert registry.recorded == []
    unresolved = registry.resolve_answer("The pond holds 1.2 acre-feet. [C2] [C9]")
    assert unresolved == ["C9"]
    assert [item["id"] for item in registry.recorded] == ["C2"]
    assert registry.recorded[0]["result"]["text"].startswith("Pond volume")


def test_evidence_block_prefers_latest_turn_and_stops_at_the_budget() -> None:
    entries = [
        {"id": "C1", "chunk_id": "a", "text": "x" * 400, "from_latest": False, "source_filename": "old.pdf", "page_start": 1},
        {"id": "C2", "chunk_id": "b", "text": "latest passage", "from_latest": True, "source_filename": "new.pdf", "page_start": 2},
    ]
    block = evidence_block(entries, budget_tokens=10_000)
    assert block.index("[C2]") < block.index("[C1]")
    short = evidence_block(entries, budget_tokens=30)
    assert "[C2]" in short
    assert "[C1]" not in short


def test_local_provider_evidence_budget_is_smaller() -> None:
    local = evidence_token_budget({"llm": {"provider": "ollama", "base_url": "http://127.0.0.1:11434"}})
    cloud = evidence_token_budget({"llm": {"provider": "openai", "base_url": "https://api.openai.com/v1"}})
    explicit = evidence_token_budget({"llm": {"provider": "ollama", "context_tokens": 32000}})
    assert local == 2_000
    assert cloud == 8_000
    assert explicit == 3_200
