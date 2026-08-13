import importlib
import sqlite3

import pytest

from vera import VeraDocument
from vera_ingest import batch_convert, convert


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

    convert(str(pdf), str(out), model="hashing", chunk_size=100, overlap=5)

    conn = sqlite3.connect(out)
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0] >= 2
    assert conn.execute(
        "SELECT COUNT(*) FROM attachments "
        "WHERE json_extract(metadata_json, '$.role')='source'"
    ).fetchone()[0] == 1

    doc = VeraDocument.open(str(out))
    info = doc.inspect()
    assert info["format_version"] == "0.2"
    assert info["pages"] == 2
    assert info["archive_size_bytes"] == out.stat().st_size
    assert info["attachments"] >= 3
    assert info["embedding_dimension"] == 384
    assert info["embedding_normalization"] == "l2"
    assert info["parser_name"] == "pymupdf"
    assert info["chunking_strategy"] == "heading_block_sliding_window:100:5"

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


def test_convert_accepts_custom_embedding_function(tmp_path):
    import numpy as np

    class TinyEmbedder:
        model_name = "example/tiny-convert"
        dimension = 2
        normalization = "l2"

        def embed(self, texts: list[str]):
            return np.asarray([[1.0, 0.0] for _ in texts], dtype=np.float32)

    pdf = tmp_path / "custom.pdf"
    out = tmp_path / "custom.vera"
    make_pdf(pdf)
    embedder = TinyEmbedder()
    convert(str(pdf), str(out), embedding_function=embedder, chunk_size=100, overlap=5)

    with VeraDocument.open(str(out), embedding_function=embedder) as doc:
        info = doc.inspect()
        assert info["embedding_model"] == "example/tiny-convert"
        assert info["embedding_dimension"] == 2
        results = doc.search("detention", mode="semantic", top_k=1)
        assert results


def test_convert_rejects_unknown_model_before_parsing(tmp_path, monkeypatch):
    from vera import UnknownEmbeddingModelError

    pdf = tmp_path / "bad-model.pdf"
    out = tmp_path / "bad-model.vera"
    make_pdf(pdf)

    def boom(*args, **kwargs):
        raise AssertionError("PDF parsing should not run for unknown models")

    pipeline_module = importlib.import_module("vera_ingest_pymupdf.pipeline")
    monkeypatch.setattr(pipeline_module, "parse_pdf_structured", boom)
    with pytest.raises(UnknownEmbeddingModelError):
        convert(str(pdf), str(out), model="not-a-real-provider:model")
    assert not out.exists()


def test_batch_convert_rejects_unknown_model_up_front(tmp_path):
    from vera import UnknownEmbeddingModelError

    pdf = tmp_path / "batch.pdf"
    make_pdf(pdf)
    with pytest.raises(UnknownEmbeddingModelError):
        batch_convert(str(tmp_path), model="not-a-real-provider:model")


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
    convert_module = importlib.import_module("vera_ingest.convert")

    def fail_create(*_args, **_kwargs):
        raise RuntimeError("simulated interrupted conversion")

    monkeypatch.setattr(convert_module.VeraDocument, "create", fail_create)

    with pytest.raises(RuntimeError, match="simulated interrupted conversion"):
        convert(str(pdf), str(out), model="hashing")

    assert out.read_bytes() == b"existing destination"
    assert list(tmp_path.glob(f".{out.name}.*.tmp")) == []


def test_convert_validation_failure_is_not_published(tmp_path, monkeypatch):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    out.write_bytes(b"existing destination")
    convert_module = importlib.import_module("vera_ingest.convert")
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


def test_batch_convert_accepts_explicit_pdf_paths(tmp_path):
    keep = tmp_path / "keep.pdf"
    skip_sibling = tmp_path / "sibling.pdf"
    nested = tmp_path / "nested" / "nested.pdf"
    nested.parent.mkdir()
    make_pdf(keep)
    make_pdf(skip_sibling)
    make_pdf(nested)

    report = batch_convert(
        paths=[str(keep), str(nested)],
        model="hashing",
    )

    assert report["discovered"] == 2
    assert report["converted"] == 2
    assert report["recursive"] is False
    assert report["directory"] == str(tmp_path.resolve())
    assert (tmp_path / "keep.vera").is_file()
    assert (nested.parent / "nested.vera").is_file()
    assert not (tmp_path / "sibling.vera").exists()


def test_batch_convert_skips_valid_output_without_original_asset(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", store_original=False)

    report = batch_convert(str(tmp_path), model="hashing", store_original=False)

    assert report["skipped_existing"] == [str(out)]
    assert report["malformed_existing"] == []


def test_batch_convert_skips_unchanged_pdf_and_reconverts_changed_source(tmp_path):
    unchanged_pdf = tmp_path / "unchanged.pdf"
    changed_pdf = tmp_path / "changed.pdf"
    unchanged_out = tmp_path / "unchanged.vera"
    changed_out = tmp_path / "changed.vera"
    make_pdf(unchanged_pdf)
    make_pdf(changed_pdf)
    convert(str(unchanged_pdf), str(unchanged_out), model="hashing")
    convert(str(changed_pdf), str(changed_out), model="hashing")
    previous = VeraDocument.open(str(changed_out))
    try:
        previous_hash = previous.inspect()["source_file_hash"]
    finally:
        previous.close()

    import fitz

    rewritten = fitz.open()
    page = rewritten.new_page()
    page.insert_text((72, 72), "Revised zoning text about loading docks and aisle width.")
    rewritten.save(changed_pdf)
    rewritten.close()

    report = batch_convert(str(tmp_path), model="hashing", overwrite=False)

    assert report["skipped_existing"] == [str(unchanged_out)]
    assert report["converted"] == 1
    assert report["outputs"] == [str(changed_out)]
    assert report["malformed_existing"] == []

    updated = VeraDocument.open(str(changed_out))
    try:
        assert updated.inspect()["source_file_hash"] != previous_hash
    finally:
        updated.close()


def test_batch_convert_reconverts_when_source_hash_is_missing(tmp_path):
    pdf = tmp_path / "manual.pdf"
    out = tmp_path / "manual.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing")
    document = VeraDocument.open(str(out), mode="write")
    try:
        metadata = dict(document.metadata)
        metadata.pop("source_file_hash", None)
        document.set_metadata(metadata)
    finally:
        document.close()

    report = batch_convert(str(tmp_path), model="hashing", overwrite=False)

    assert report["skipped_existing"] == []
    assert report["converted"] == 1
    assert report["outputs"] == [str(out)]
    restored = VeraDocument.open(str(out))
    try:
        assert restored.inspect()["source_file_hash"]
    finally:
        restored.close()


def test_batch_convert_reports_progress_for_each_discovered_pdf(tmp_path):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    make_pdf(first_pdf)
    make_pdf(second_pdf)
    progress = []

    batch_convert(
        str(tmp_path),
        model="hashing",
        progress=lambda completed, total, input_path: progress.append((completed, total, input_path)),
    )

    assert progress == [
        (0, 2, str(first_pdf)),
        (1, 2, str(second_pdf)),
        (2, 2, str(second_pdf)),
    ]


def test_batch_convert_stops_when_cancelled(tmp_path, monkeypatch):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    make_pdf(first_pdf)
    make_pdf(second_pdf)

    class Token:
        def __init__(self):
            self.cancelled = False

        def raise_if_cancelled(self):
            if self.cancelled:
                raise RuntimeError("Conversion cancelled")

        def raise_if_interrupted(self):
            self.raise_if_cancelled()

    cancel = Token()
    convert_mod = importlib.import_module("vera_ingest.convert")
    real_convert = convert_mod.convert

    def convert_once(input_path, output_path, **kwargs):
        kwargs = dict(kwargs)
        kwargs.pop("cancel", None)
        output = real_convert(input_path, output_path, **kwargs)
        cancel.cancelled = True
        return output

    monkeypatch.setattr(convert_mod, "convert", convert_once)

    with pytest.raises(RuntimeError, match="Conversion cancelled"):
        batch_convert(str(tmp_path), model="hashing", cancel=cancel)

    assert (tmp_path / "first.vera").is_file()
    assert not (tmp_path / "second.vera").exists()


def test_batch_convert_skips_current_file_and_continues(tmp_path, monkeypatch):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    make_pdf(first_pdf)
    make_pdf(second_pdf)

    class Token:
        def __init__(self):
            self.cancelled = False
            self.skip_requested = False

        def raise_if_cancelled(self):
            if self.cancelled:
                raise RuntimeError("Conversion cancelled")

        def raise_if_interrupted(self):
            self.raise_if_cancelled()
            if self.skip_requested:
                raise RuntimeError("File skipped")

        def clear_skip(self):
            self.skip_requested = False

    cancel = Token()
    convert_mod = importlib.import_module("vera_ingest.convert")
    real_convert = convert_mod.convert
    calls = {"n": 0}

    def convert_with_skip(input_path, output_path, **kwargs):
        calls["n"] += 1
        kwargs = dict(kwargs)
        kwargs.pop("cancel", None)
        if calls["n"] == 1:
            cancel.skip_requested = True
            cancel.raise_if_interrupted()
        return real_convert(input_path, output_path, **kwargs)

    monkeypatch.setattr(convert_mod, "convert", convert_with_skip)

    report = batch_convert(str(tmp_path), model="hashing", cancel=cancel)

    assert report["converted"] == 1
    assert report["user_skipped"] == 1
    assert report["skipped_by_user"] == [str(first_pdf)]
    assert report["failed"] == 0
    assert not (tmp_path / "first.vera").exists()
    assert (tmp_path / "second.vera").is_file()


def test_hybrid_keeps_chunk_that_tops_both_modes(tmp_path):
    """Regression: a chunk ranked #1 by both semantic and keyword search must
    rank #1 in hybrid. The old fusion buried dual-mode winners behind chunks
    that merely appeared in both candidate pools."""
    pdf = tmp_path / "ordinance.pdf"
    out = tmp_path / "ordinance.vera"
    make_pdf(pdf)
    convert(str(pdf), str(out), model="hashing", chunk_size=100, overlap=5)

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
    convert(str(pdf), str(out), model="hashing", chunk_size=100, overlap=5)

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
    convert(str(pdf), str(out), model="hashing", chunk_size=100, overlap=5)

    doc = VeraDocument.open(str(out))
    with pytest.raises(ValueError, match="context_chunks"):
        doc.search("restaurant parking", context_chunks=-1)
    doc.close()
