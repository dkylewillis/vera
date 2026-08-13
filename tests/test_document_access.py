"""Tests for ingest viewer helpers (source document, pages, blocks, regions)."""

import json
import subprocess
import sys

import pytest

from test_blocks_figures import make_structured_pdf
from vera_doc import AttachmentRecord, VeraDocument
from vera_ingest import convert
from vera_ingest.viewer import (
    export_source_document,
    figures_for,
    get_blocks,
    get_chunk_regions,
    get_page,
    get_source_document,
    regions_for,
)


@pytest.fixture
def vera_doc(tmp_path):
    pdf = tmp_path / "structured.pdf"
    make_structured_pdf(pdf)
    out = tmp_path / "structured.vera"
    convert(str(pdf), str(out), model="hashing")
    doc = VeraDocument.open(str(out))
    yield doc, pdf, out
    doc.close()


class TestGetSourceDocument:
    def test_returns_original_bytes(self, vera_doc):
        doc, pdf, _ = vera_doc
        source = get_source_document(doc)
        assert isinstance(source, AttachmentRecord)
        assert source.data == pdf.read_bytes()

    def test_metadata_fields(self, vera_doc):
        doc, pdf, _ = vera_doc
        source = get_source_document(doc)
        assert source.filename == pdf.name
        assert source.media_type == "application/pdf"
        assert source.checksum == doc.inspect()["source_file_hash"]

    def test_raises_when_original_not_stored(self, tmp_path):
        pdf = tmp_path / "nosave.pdf"
        make_structured_pdf(pdf)
        out = tmp_path / "nosave.vera"
        convert(str(pdf), str(out), model="hashing", store_original=False)
        doc = VeraDocument.open(str(out))
        try:
            with pytest.raises(ValueError):
                get_source_document(doc)
        finally:
            doc.close()


class TestExportSourceDocument:
    def test_export_to_explicit_path(self, vera_doc, tmp_path):
        doc, pdf, _ = vera_doc
        target = tmp_path / "exported" / "copy.pdf"
        written = export_source_document(doc, str(target))
        assert written == str(target)
        assert target.read_bytes() == pdf.read_bytes()

    def test_export_to_directory_uses_stored_filename(self, vera_doc, tmp_path):
        doc, pdf, _ = vera_doc
        outdir = tmp_path / "outdir"
        outdir.mkdir()
        written = export_source_document(doc, str(outdir))
        assert written == str(outdir / pdf.name)
        assert (outdir / pdf.name).read_bytes() == pdf.read_bytes()

    def test_export_rejects_parent_and_absolute_stored_names(self, vera_doc, tmp_path, monkeypatch):
        from vera_doc import AttachmentRecord
        from vera_ingest import viewer as viewer_mod

        doc, _, _ = vera_doc
        real = get_source_document(doc)
        parent = AttachmentRecord(
            id=real.id,
            data=real.data,
            media_type=real.media_type,
            filename="../evil.pdf",
        )
        monkeypatch.setattr(viewer_mod, "get_source_document", lambda document: parent)
        with pytest.raises(ValueError, match="safe relative name"):
            export_source_document(doc, str(tmp_path))

        absolute = AttachmentRecord(
            id=real.id,
            data=real.data,
            media_type=real.media_type,
            filename=str(tmp_path / "outside.pdf"),
        )
        monkeypatch.setattr(viewer_mod, "get_source_document", lambda document: absolute)
        with pytest.raises(ValueError, match="safe relative name"):
            export_source_document(doc, str(tmp_path))


class TestGetPage:
    def test_returns_text_and_dimensions(self, vera_doc):
        doc, _, _ = vera_doc
        page = get_page(doc, 1)
        assert page["page_number"] == 1
        assert "Zoning" in page["text"]
        assert page["width"] > 0
        assert page["height"] > 0

    def test_missing_page_returns_none(self, vera_doc):
        doc, _, _ = vera_doc
        assert get_page(doc, 99) is None


class TestGetBlocks:
    def test_all_blocks_in_reading_order(self, vera_doc):
        doc, _, _ = vera_doc
        blocks = get_blocks(doc)
        assert blocks
        orders = [b["sort_order"] for b in blocks]
        assert orders == sorted(orders)
        types = {b["block_type"] for b in blocks}
        assert "heading" in types
        assert "paragraph" in types

    def test_filter_by_page(self, vera_doc):
        doc, _, _ = vera_doc
        blocks = get_blocks(doc, page_number=2)
        assert blocks
        assert all(b["page_number"] == 2 for b in blocks)

    def test_bbox_parsed_as_list(self, vera_doc):
        doc, _, _ = vera_doc
        blocks = get_blocks(doc, page_number=1)
        boxed = [b for b in blocks if b["bbox"] is not None]
        assert boxed
        assert len(boxed[0]["bbox"]) == 4


class TestChunkRegions:
    def test_regions_have_bbox_and_page_dimensions(self, vera_doc):
        doc, _, _ = vera_doc
        chunk = doc.search(text="restaurant parking", mode="keyword", top_k=1)[0]
        regions = get_chunk_regions(doc, chunk.record.id)
        assert regions
        for region in regions:
            assert region["page_number"] == chunk.record.metadata["page_start"]
            assert len(region["bbox"]) == 4
            assert region["page_width"] > 0
            assert region["page_height"] > 0

    def test_unknown_chunk_returns_empty(self, vera_doc):
        doc, _, _ = vera_doc
        assert get_chunk_regions(doc, "chunk_999999") == []

    def test_regions_for_search_result(self, vera_doc):
        doc, _, _ = vera_doc
        results = doc.search(text="detention impervious", mode="keyword", top_k=1)
        assert results
        regions = regions_for(doc, results[0])
        assert regions
        pages = {r["page_number"] for r in regions}
        assert pages <= set(
            range(
                results[0].record.metadata["page_start"],
                results[0].record.metadata["page_end"] + 1,
            )
        )

    def test_regions_exclude_image_blocks(self, vera_doc):
        doc, _, _ = vera_doc
        result = doc.search(text="restaurant parking", mode="keyword", top_k=1)[0]
        image_block_ids = {
            block["block_id"] for block in get_blocks(doc) if block["block_type"] == "image"
        }
        linked = {figure["block_id"] for figure in figures_for(doc, result)}
        assert linked & image_block_ids

        regions = regions_for(doc, result)
        assert not any(r["block_id"] in image_block_ids for r in regions)


class TestCli:
    def run(self, *argv):
        proc = subprocess.run(
            [sys.executable, "-m", "vera_cli", *argv],
            capture_output=True,
            text=True,
        )
        return proc

    def test_export_command(self, vera_doc, tmp_path):
        _, pdf, out = vera_doc
        target = tmp_path / "cli_export.pdf"
        proc = self.run("export", str(out), str(target), "--json")
        assert proc.returncode == 0, proc.stderr
        payload = json.loads(proc.stdout)
        assert payload["ok"] is True
        assert target.read_bytes() == pdf.read_bytes()
