"""Tests for public page-text chunking helpers (custom pipelines)."""

import pytest

from vera_ingest.chunking import chunk_pages, detect_heading
from vera_ingest.types import ParsedPage


def _pages(*texts: str) -> list[ParsedPage]:
    """Build a list of ParsedPage objects from plain strings."""
    return [
        ParsedPage(page_number=i + 1, width=612.0, height=792.0, text=t)
        for i, t in enumerate(texts)
    ]


class TestChunkPages:
    def test_empty_pages_returns_no_chunks(self):
        assert chunk_pages([]) == []

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_pages(_pages("hello world"), chunk_size=0)

    def test_negative_chunk_size_raises(self):
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            chunk_pages(_pages("hello world"), chunk_size=-1)

    def test_page_with_empty_text_produces_no_chunks(self):
        assert chunk_pages(_pages("")) == []

    def test_page_with_only_whitespace_produces_no_chunks(self):
        assert chunk_pages(_pages("   \n\n  ")) == []

    def test_short_text_produces_one_chunk(self):
        chunks = chunk_pages(_pages("The quick brown fox."), chunk_size=500)
        assert len(chunks) == 1
        assert "fox" in chunks[0].text

    def test_chunk_page_numbers_are_preserved(self):
        chunks = chunk_pages(_pages("Page one text.", "Page two text."), chunk_size=500)
        page_numbers = {c.page_start for c in chunks}
        assert 1 in page_numbers
        assert 2 in page_numbers

    def test_large_paragraph_is_split_into_multiple_chunks(self):
        # 120 words > chunk_size=10
        words = " ".join(f"word{i}" for i in range(120))
        chunks = chunk_pages(_pages(words), chunk_size=10, overlap=2)
        assert len(chunks) > 1

    def test_overlap_is_clamped_to_chunk_size_minus_one(self):
        # overlap >= chunk_size should be clamped rather than crash
        words = " ".join(f"w{i}" for i in range(30))
        chunks = chunk_pages(_pages(words), chunk_size=5, overlap=10)
        assert len(chunks) >= 1

    def test_all_chunks_have_positive_token_count(self):
        text = " ".join(f"token{i}" for i in range(50))
        chunks = chunk_pages(_pages(text), chunk_size=10, overlap=2)
        for c in chunks:
            assert c.token_count > 0

    def test_heading_detected_from_chapter_line(self):
        text = "Chapter 3 Land Use\nSome content about land use regulations."
        chunks = chunk_pages(_pages(text), chunk_size=500)
        assert any("chapter" in (c.heading_path or "").lower() for c in chunks)

    def test_heading_detected_from_section_line(self):
        text = "Section 4.2 Zoning Districts\nContent describing the districts."
        chunks = chunk_pages(_pages(text), chunk_size=500)
        assert any("section" in (c.heading_path or "").lower() for c in chunks)

    def test_no_heading_uses_empty_string(self):
        chunks = chunk_pages(_pages("Just some plain text with no heading."), chunk_size=500)
        assert chunks[0].heading_path == ""


class TestDetectHeading:
    def test_chapter_line_detected(self):
        result = detect_heading("Chapter 1 Introduction\nText here.", "")
        assert "Chapter" in result

    def test_non_heading_line_returns_current(self):
        result = detect_heading("This is just a sentence.", "current heading")
        assert result == "current heading"

    def test_very_long_line_is_not_a_heading(self):
        long_line = "word " * 30  # > 120 chars
        result = detect_heading(long_line.strip(), "old heading")
        assert result == "old heading"
