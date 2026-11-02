"""Markdown report footnotes, filenames, and versioned drafts."""

from __future__ import annotations

from vera_app.citations import CitationRegistry
from vera_app.markdown_drafts import (
    current_draft_block,
    render_report,
    safe_markdown_name,
    write_draft,
)


def _registry() -> CitationRegistry:
    registry = CitationRegistry()
    registry.seed_request(
        {
            "prior_evidence": [
                {
                    "id": "C1",
                    "chunk_id": "chunk_0001",
                    "file": "manual.vera",
                    "text": "Pond volume is 1.2 acre-feet.",
                    "page_start": 117,
                    "heading_path": "Chapter 4 > 4.2 Detention Design",
                    "source_filename": "manual.pdf",
                }
            ]
        }
    )
    return registry


def test_render_report_turns_citations_into_footnotes() -> None:
    text, missing = render_report("Pond memo", "The pond is sized. [C1] [C1] [C9]", _registry())
    assert missing == ["C9"]
    assert "[^1]" in text
    assert "[C1]" not in text
    assert "manual.pdf, p. 117, Chapter 4 > 4.2 Detention Design" in text
    assert 'title: "Pond memo"' in text
    assert text.count("[^1]") == 3  # two markers plus the definition


def test_filename_is_forced_to_markdown_and_cannot_escape() -> None:
    assert safe_markdown_name(r"..\..\windows\report.docx") == "report.md"
    assert safe_markdown_name("quarterly report") == "quarterly report.md"


def test_write_draft_versions_and_stays_in_the_folder(tmp_path) -> None:
    first = write_draft(str(tmp_path), "sess", "report.md", "one")
    second = write_draft(str(tmp_path), "sess", "report.md", "two")
    assert first["version"] == 1
    assert second["version"] == 2
    assert second["filename"] == "report.v2.md"
    assert str(tmp_path) in first["path"]
    escaped = write_draft(str(tmp_path), "..", "report.md", "nope")
    assert escaped["path"].startswith(str(tmp_path))


def test_current_draft_is_fed_back_as_raw_text(tmp_path) -> None:
    saved = write_draft(str(tmp_path), "sess", "report.md", "The pond is sized. [^1]")
    block = current_draft_block(
        {"drafts_dir": str(tmp_path), "current_drafts": [{"path": saved["path"], "filename": saved["filename"]}]}
    )
    assert "Current draft (report.md)" in block
    assert "[^1]" in block
    assert current_draft_block({"drafts_dir": str(tmp_path), "current_drafts": [{"path": str(tmp_path.parent / "x.md")}]}) == ""
