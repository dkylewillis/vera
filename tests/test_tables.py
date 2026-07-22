"""Tests for pdfplumber table extraction and overlap merge."""

import sqlite3

import pytest

from vera import VeraDocument, convert
from vera.ingest.chunking import build_chunks_from_blocks
from vera.ingest.parsers import ParsedBlock, parse_pdf_structured
from vera.ingest.parsers.pdf import (
    _merge_tables_into_blocks,
    _overlap_fraction,
    _table_to_markdown,
)


def make_bordered_table_pdf(path):
    """PDF with a ruled table and surrounding prose."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    table = Table(
        [
            ["Use Type", "Required Spaces"],
            ["Restaurant", "1 per 100 sf"],
            ["Retail", "1 per 200 sf"],
        ],
        colWidths=[180, 180],
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    doc.build(
        [
            Paragraph("Parking Requirements", styles["Heading2"]),
            Spacer(1, 12),
            table,
            Spacer(1, 12),
            Paragraph("Additional notes follow the table.", styles["Normal"]),
        ]
    )


@pytest.fixture
def table_pdf(tmp_path):
    pdf = tmp_path / "table.pdf"
    make_bordered_table_pdf(pdf)
    return pdf


class TestTableMarkdown:
    def test_table_to_markdown_formats_header_and_rows(self):
        markdown = _table_to_markdown(
            [
                ["Use Type", "Required Spaces"],
                ["Restaurant", "1 per 100 sf"],
            ]
        )
        assert markdown.splitlines()[0] == "| Use Type | Required Spaces |"
        assert "| --- | --- |" in markdown
        assert "| Restaurant | 1 per 100 sf |" in markdown

    def test_table_to_markdown_escapes_pipes(self):
        markdown = _table_to_markdown([["A|B", "Value"]])
        assert r"A\|B" in markdown


class TestOverlapMerge:
    def test_overlap_fraction_is_one_for_identical_boxes(self):
        bbox = (10.0, 20.0, 100.0, 120.0)
        assert _overlap_fraction(bbox, bbox) == 1.0

    def test_merge_drops_overlapping_paragraphs(self):
        table_bbox = (72.0, 120.0, 300.0, 220.0)
        blocks = [
            ParsedBlock(1, "heading", "Parking Requirements", bbox=(72.0, 72.0, 250.0, 95.0)),
            ParsedBlock(
                1,
                "paragraph",
                "Restaurant 1 per 100 sf Retail 1 per 200 sf",
                bbox=(75.0, 130.0, 290.0, 210.0),
            ),
            ParsedBlock(
                1,
                "paragraph",
                "Additional notes follow the table.",
                bbox=(72.0, 250.0, 350.0, 270.0),
            ),
        ]
        tables = [
            {
                "table_text": "| Use Type | Required Spaces |",
                "page_number": 1,
                "table_index": 0,
                "bbox": table_bbox,
            }
        ]
        merged = _merge_tables_into_blocks(blocks, tables)
        types = [block.block_type for block in merged]
        assert types.count("table") == 1
        assert types.count("paragraph") == 1
        assert "Additional notes" in merged[-1].text


class TestParsePdfTables:
    def test_extracts_table_block_from_bordered_pdf(self, table_pdf):
        _, blocks = parse_pdf_structured(str(table_pdf))
        tables = [block for block in blocks if block.block_type == "table"]
        assert len(tables) == 1
        assert "Use Type" in tables[0].text
        assert "Restaurant" in tables[0].text
        assert tables[0].bbox is not None

    def test_table_block_sorted_after_heading_before_trailing_paragraph(self, table_pdf):
        _, blocks = parse_pdf_structured(str(table_pdf))
        types = [block.block_type for block in blocks]
        assert types.index("heading") < types.index("table") < types.index("paragraph")

    def test_overlapping_garbled_table_paragraph_is_removed(self, table_pdf):
        _, blocks = parse_pdf_structured(str(table_pdf))
        paragraphs = [block.text for block in blocks if block.block_type == "paragraph"]
        assert any("Additional notes" in text for text in paragraphs)
        assert not any("Restaurant" in text and "Retail" in text for text in paragraphs)

    def test_table_markdown_is_chunked_and_searchable(self, tmp_path, table_pdf):
        out = tmp_path / "out.vera"
        convert(str(table_pdf), str(out), model="hashing")
        doc = VeraDocument.open(str(out))
        try:
            results = doc.search("restaurant 100 sf", mode="keyword", top_k=1)
            assert results
            assert "restaurant" in results[0].text.lower()
        finally:
            doc.close()

    def test_table_blocks_persisted_in_vera_file(self, tmp_path, table_pdf):
        out = tmp_path / "out.vera"
        convert(str(table_pdf), str(out), model="hashing")
        conn = sqlite3.connect(out)
        try:
            count = conn.execute("SELECT COUNT(*) FROM blocks WHERE block_type='table'").fetchone()[0]
            assert count == 1
        finally:
            conn.close()


class TestTableChunking:
    def test_table_flushes_preceding_paragraph(self):
        blocks = [
            ("b1", ParsedBlock(1, "paragraph", "Intro text before the table.")),
            ("b2", ParsedBlock(1, "table", "| A | B |\n| --- | --- |\n| 1 | 2 |")),
        ]
        chunks = build_chunks_from_blocks(blocks)
        assert len(chunks) == 2
        assert chunks[0].text == "Intro text before the table."
        assert "| A | B |" in chunks[1].text
