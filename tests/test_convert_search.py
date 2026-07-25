import importlib
import sqlite3

import pytest

from vera import VeraDocument, batch_convert, convert


def make_pdf(path):
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Chapter 110 Zoning\nRestaurants require one parking space per 100 square feet.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Stormwater Manual\nDetention is required when impervious area increases.")
    doc.save(path)
    doc.close()


def make_context_pdf(path):
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Opening Context\nAlpha approach overview precedes the target section.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "Middle Target\nBeacon target language lives in this middle section.")
    page3 = doc.new_page()
    page3.insert_text((72, 72), "Closing Context\nOmega followup details come after the target section.")
    doc.save(path)
    doc.close()


def make_textless_pdf(path):
    import fitz

    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()


def test_convert_pdf_populates_vera_and_searches(tmp_path):
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)

    convert(str(pdf), str(out), model="hashing", chunk_size=40, overlap=5)

    conn = sqlite3.connect(out)
    assert conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM pages").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM assets WHERE asset_type='original_document'").fetchone()[0] == 1

    doc = VeraDocument.open(str(out))
    info = doc.inspect()
    assert info["format_version"] == "0.1"
    assert info["pages"] == 2

    keyword = doc.search("restaurant parking", mode="keyword", top_k=1)[0]
    assert "parking" in keyword.text.lower()
    assert keyword.page_start == 1

    semantic = doc.search("detention impervious area", mode="semantic", top_k=1)[0]
    assert "detention" in semantic.text.lower()
    assert semantic.page_start == 2

    hybrid = doc.search("streamwater detention required", mode="hybrid", top_k=2)
    assert hybrid
    assert hybrid[0].score >= hybrid[-1].score
    doc.close()


def test_convert_rejects_textless_pdf_without_publishing_output(tmp_path):
    pdf = tmp_path / "scan.pdf"
    out = tmp_path / "scan.vera"
    make_textless_pdf(pdf)

    with pytest.raises(ValueError, match="scanned and requires OCR"):
        convert(str(pdf), str(out), model="hashing")

    assert not out.exists()


def test_convert_failure_preserves_destination_and_removes_temporary_file(
    tmp_path, monkeypatch
):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    out.write_bytes(b"existing destination")
    convert_module = importlib.import_module("vera.convert")

    def fail_schema(_conn):
        raise RuntimeError("simulated interrupted conversion")

    monkeypatch.setattr(convert_module, "create_schema", fail_schema)

    with pytest.raises(RuntimeError, match="simulated interrupted conversion"):
        convert(str(pdf), str(out), model="hashing")

    assert out.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(f".{out.name}.*.tmp")) == []


def test_convert_validation_failure_is_not_published(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    out.write_bytes(b"existing destination")
    convert_module = importlib.import_module("vera.convert")
    monkeypatch.setattr(
        convert_module,
        "validate_document",
        lambda _conn: {"ok": False, "issues": ["simulated validation failure"]},
    )

    with pytest.raises(ValueError, match="simulated validation failure"):
        convert(str(pdf), str(out), model="hashing")

    assert out.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(f".{out.name}.*.tmp")) == []


def test_batch_convert_reports_malformed_existing_output(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    sqlite3.connect(out).close()

    report = batch_convert(str(tmp_path), model="hashing")

    assert report["converted"] == 0
    assert report["skipped"] == 0
    assert report["malformed"] == 1
    assert report["malformed_existing"][0]["output"] == str(out)
    assert "Missing required table: vera_metadata" in report["malformed_existing"][0]["issues"]


def test_batch_convert_skips_valid_output_without_original_asset(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=False)

    report = batch_convert(str(tmp_path), model="hashing", store_original=False)

    assert report["skipped_existing"] == [str(out)]
    assert report["malformed_existing"] == []


def test_hybrid_keeps_chunk_that_tops_both_modes(tmp_path):
    """Regression: a chunk ranked #1 by both semantic and keyword search must
    rank #1 in hybrid. The old fusion buried dual-mode winners behind chunks
    that merely appeared in both candidate pools."""
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", chunk_size=40, overlap=5)

    doc = VeraDocument.open(str(out))
    query = "restaurant parking space requirements"
    top_sem = doc.search(query, mode="semantic", top_k=1)[0]
    top_key = doc.search(query, mode="keyword", top_k=1)[0]
    if top_sem.chunk_id == top_key.chunk_id:
        top_hybrid = doc.search(query, mode="hybrid", top_k=1)[0]
        assert top_hybrid.chunk_id == top_sem.chunk_id
    doc.close()


def test_search_can_include_context_chunks(tmp_path):
    pdf = tmp_path / "context.pdf"
    out = tmp_path / "context.vera"
    make_context_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", chunk_size=80, overlap=5)

    doc = VeraDocument.open(str(out))
    default = doc.search("beacon target", mode="keyword", top_k=1)[0]
    assert "before_chunks" not in default.as_dict()
    assert "after_chunks" not in default.as_dict()

    result = doc.search("beacon target", mode="keyword", top_k=1, context_chunks=1)[0]
    assert "beacon target" in result.text.lower()
    assert result.before_chunks is not None
    assert result.after_chunks is not None
    assert len(result.before_chunks) == 1
    assert len(result.after_chunks) == 1
    assert "alpha approach" in result.before_chunks[0]["text"].lower()
    assert "omega followup" in result.after_chunks[0]["text"].lower()
    assert result.chunk_id not in {result.before_chunks[0]["chunk_id"], result.after_chunks[0]["chunk_id"]}
    assert "score" not in result.before_chunks[0]
    doc.close()


def test_search_rejects_negative_context_chunks(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", chunk_size=40, overlap=5)

    doc = VeraDocument.open(str(out))
    with pytest.raises(ValueError, match="context_chunks"):
        doc.search("restaurant parking", context_chunks=-1)
    doc.close()
