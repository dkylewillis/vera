"""Tests for vera-lab lint, stats, report payload, and archive round-trip."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers.pdfs import make_structured_pdf
from vera_ingest import convert
from vera_ingest.types import IngestBlock, IngestChunk, IngestResult, ParsedPage
from vera_lab.archive import load_archive_document
from vera_lab.cli import main as lab_main
from vera_lab.lint import lint_document, lint_ingest_result
from vera_lab.model import LabBlock, LabChunk, LabDocument, LabPage, lab_document_from_ingest_result
from vera_lab.report import build_report
from vera_lab.run import load_live_document, validate_pipeline_options
from vera_lab.stats import compute_stats


def _minimal_result(**overrides) -> IngestResult:
    pages = overrides.pop(
        "pages",
        [ParsedPage(page_number=1, width=612.0, height=792.0, text="Hello")],
    )
    blocks = overrides.pop(
        "blocks",
        [
            IngestBlock(
                block_id="block_000001",
                page_number=1,
                block_type="paragraph",
                text="Hello",
                bbox=(72.0, 72.0, 200.0, 100.0),
            )
        ],
    )
    chunks = overrides.pop(
        "chunks",
        [
            IngestChunk(
                chunk_id="chunk_000001",
                text="Hello",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=1,
                block_ids=["block_000001"],
            )
        ],
    )
    return IngestResult(
        pages=pages,
        blocks=blocks,
        chunks=chunks,
        parser_name=overrides.pop("parser_name", "test"),
        parser_version=overrides.pop("parser_version", "0.0"),
        chunking_strategy=overrides.pop("chunking_strategy", "test"),
        diagnostics=overrides.pop("diagnostics", {}),
    )


def test_lint_ingest_result_reports_all_convert_invariants():
    result = _minimal_result(
        blocks=[
            IngestBlock(block_id="", page_number=1, block_type="paragraph", text="a"),
            IngestBlock(block_id="dup", page_number=1, block_type="paragraph", text="b"),
            IngestBlock(block_id="dup", page_number=1, block_type="paragraph", text="c"),
        ],
        chunks=[
            IngestChunk(
                chunk_id="",
                text="x",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=1,
                block_ids=["missing"],
            ),
            IngestChunk(
                chunk_id="same",
                text="   ",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=0,
                block_ids=["dup"],
            ),
            IngestChunk(
                chunk_id="same",
                text="ok",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=1,
                block_ids=["dup"],
            ),
        ],
    )
    codes = {issue.code for issue in lint_ingest_result(result)}
    assert "empty_block_id" in codes
    assert "duplicate_block_id" in codes
    assert "empty_chunk_id" in codes
    assert "duplicate_chunk_id" in codes
    assert "unknown_block_ids" in codes
    assert "empty_chunk_text" in codes


def test_lint_ingest_result_parity_with_convert_validator():
    """When convert would raise, lab reports a matching error code/message fragment."""
    from vera_ingest.convert import _validate_ingest_result

    bad = _minimal_result(
        chunks=[
            IngestChunk(
                chunk_id="chunk_000001",
                text="",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=0,
                block_ids=["block_000001"],
            )
        ]
    )
    with pytest.raises(ValueError, match="no readable text"):
        _validate_ingest_result(bad)
    issues = lint_ingest_result(bad)
    assert any(issue.code == "empty_chunk_text" for issue in issues)


def test_layout_lint_rules_fire_on_seeded_violations():
    document = LabDocument(
        source_path="x.pdf",
        source_bytes=b"%PDF",
        pages=[
            LabPage(page_number=1, width=612.0, height=792.0, text=""),
            LabPage(page_number=2, width=612.0, height=792.0, text=""),
        ],
        blocks=[
            LabBlock(
                block_id="img1",
                page_number=1,
                block_type="image",
                text="",
                bbox=[10.0, 10.0, 50.0, 50.0],
                has_image=True,
            ),
            LabBlock(
                block_id="para1",
                page_number=1,
                block_type="paragraph",
                text="orphan",
                bbox=None,
            ),
            LabBlock(
                block_id="table1",
                page_number=1,
                block_type="table",
                text="| a |",
                bbox=[0.0, 0.0, 0.0, 10.0],
            ),
            LabBlock(
                block_id="cap1",
                page_number=2,
                block_type="caption",
                text="Figure 1",
                bbox=[60.0, 60.0, 100.0, 80.0],
            ),
            LabBlock(
                block_id="linked",
                page_number=1,
                block_type="paragraph",
                text="covered but no bbox",
                bbox=None,
            ),
            LabBlock(
                block_id="ov1",
                page_number=1,
                block_type="paragraph",
                text="a",
                bbox=[200.0, 200.0, 300.0, 300.0],
            ),
            LabBlock(
                block_id="ov2",
                page_number=1,
                block_type="paragraph",
                text="b",
                bbox=[205.0, 205.0, 295.0, 295.0],
            ),
        ],
        chunks=[
            LabChunk(
                chunk_id="c1",
                text="covered but no bbox",
                page_start=1,
                page_end=2,
                heading_path="",
                token_count=4,
                block_ids=["linked", "ov1", "ov2"],
            )
        ],
        figures=[],
    )
    codes = {issue.code for issue in lint_document(document)}
    assert "unlinked_image_block" in codes
    assert "uncovered_block" in codes
    assert "orphan_table_text" in codes
    assert "caption_without_figure" in codes
    assert "cross_page_chunk" in codes
    assert "missing_bbox" in codes
    assert "degenerate_bbox" in codes
    assert "overlapping_bboxes" in codes


def test_stats_token_histogram_and_counts():
    document = LabDocument(
        source_path="x.pdf",
        source_bytes=b"%PDF",
        pages=[LabPage(page_number=1, width=1.0, height=1.0, text="")],
        blocks=[
            LabBlock(block_id="b1", page_number=1, block_type="paragraph", text="a"),
            LabBlock(block_id="b2", page_number=1, block_type="heading", text="H"),
        ],
        chunks=[
            LabChunk(
                chunk_id="c1",
                text="one two",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=10,
                block_ids=["b1"],
            ),
            LabChunk(
                chunk_id="c2",
                text="three",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=60,
                block_ids=["b1", "b2"],
            ),
        ],
        figures=[],
    )
    stats = compute_stats(document)
    assert stats["block_count"] == 2
    assert stats["chunk_count"] == 2
    assert stats["blocks_by_type"] == {"heading": 1, "paragraph": 1}
    assert stats["token_count"]["min"] == 10
    assert stats["token_count"]["max"] == 60
    assert stats["token_count"]["median"] == 35.0
    assert stats["chunk_block_linkage"]["single_block"] == 1
    assert stats["chunk_block_linkage"]["multi_block"] == 1
    assert stats["token_count"]["histogram"]


def test_live_report_payload_keys(tmp_path: Path):
    pdf = make_structured_pdf(tmp_path / "sample.pdf")
    output = tmp_path / "report.html"
    build_report(pdf, output, parsers=["pymupdf"], dpi=72, max_pages=2)
    html = output.read_text(encoding="utf-8")
    assert "window.__VERA_LAB__" in html
    start = html.index("window.__VERA_LAB__ = ") + len("window.__VERA_LAB__ = ")
    end = html.index(";\n", start)
    payload = json.loads(html[start:end])
    assert "runs" in payload
    assert "selected_pages" in payload
    run = payload["runs"][0]
    assert set(run) >= {"label", "document", "issues", "stats", "rendered_pages"}
    document = run["document"]
    assert set(document) >= {
        "pages",
        "blocks",
        "chunks",
        "figures",
        "parser_name",
        "mode",
    }
    assert document["mode"] == "live"
    assert run["rendered_pages"]


def test_archive_round_trip(tmp_path: Path):
    pdf = make_structured_pdf(tmp_path / "sample.pdf")
    archive = tmp_path / "sample.vera"
    convert(str(pdf), str(archive), model="hashing", store_original=True, parser="pymupdf")
    document = load_archive_document(archive)
    assert document.mode == "archive"
    assert document.pages
    assert document.chunks
    assert document.source_bytes.startswith(b"%PDF")
    output = tmp_path / "archive.html"
    build_report(archive, output, dpi=72, max_pages=2)
    assert output.is_file()
    assert "archive" in output.read_text(encoding="utf-8")


def test_compare_mode_emits_multiple_runs(tmp_path: Path):
    pdf = make_structured_pdf(tmp_path / "sample.pdf")
    output = tmp_path / "compare.html"
    # Comparing the same parser twice should de-dupe to one run.
    build_report(pdf, output, parsers=["pymupdf", "pymupdf"], dpi=72, max_pages=1)
    html = output.read_text(encoding="utf-8")
    start = html.index("window.__VERA_LAB__ = ") + len("window.__VERA_LAB__ = ")
    end = html.index(";\n", start)
    payload = json.loads(html[start:end])
    assert len(payload["runs"]) == 1


def test_cli_writes_report(tmp_path: Path):
    pdf = make_structured_pdf(tmp_path / "sample.pdf")
    output = tmp_path / "cli.html"
    assert lab_main([str(pdf), "-o", str(output), "--dpi", "72", "--max-pages", "1"]) == 0
    assert output.is_file()


def test_validate_pipeline_options_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown pipeline option"):
        validate_pipeline_options("pymupdf", {"not_a_real_option": 1})


def test_region_derivation_skips_image_blocks(tmp_path: Path):
    pdf = make_structured_pdf(tmp_path / "sample.pdf", with_image=True)
    document = load_live_document(pdf, parser="pymupdf")
    for chunk in document.chunks:
        for region in chunk.regions:
            block = next(b for b in document.blocks if b.block_id == region.block_id)
            assert block.block_type != "image"


def test_lab_document_from_ingest_result_copies_figures():
    result = _minimal_result(
        blocks=[
            IngestBlock(
                block_id="img",
                page_number=1,
                block_type="image",
                text="",
                bbox=(10.0, 10.0, 40.0, 40.0),
                image_bytes=b"\x89PNG\r\n\x1a\n",
                image_ext="png",
            ),
            IngestBlock(
                block_id="cap",
                page_number=1,
                block_type="caption",
                text="A figure",
                bbox=(10.0, 50.0, 40.0, 60.0),
            ),
            IngestBlock(
                block_id="p1",
                page_number=1,
                block_type="paragraph",
                text="body",
                bbox=(10.0, 70.0, 100.0, 90.0),
            ),
        ],
        chunks=[
            IngestChunk(
                chunk_id="c1",
                text="body",
                page_start=1,
                page_end=1,
                heading_path="",
                token_count=1,
                block_ids=["p1", "img"],
            )
        ],
    )
    document = lab_document_from_ingest_result(
        result,
        source_path="x.pdf",
        source_bytes=b"%PDF",
        pipeline_spec="test",
    )
    assert len(document.figures) == 1
    assert document.figures[0].caption == "A figure"
    assert document.figures[0].data_url
