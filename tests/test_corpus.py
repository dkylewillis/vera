"""Tests for corpus search across a folder of .vera files."""

import json
import sqlite3
import subprocess
import sys

import pytest

from vera import CorpusSearchResult, VeraCorpus
from vera_ingest import convert
from vera_ingest.viewer import regions_for


def make_topic_pdf(path, heading, body):
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), heading, fontsize=20)
    page.insert_text((72, 110), body, fontsize=11)
    doc.save(path)
    doc.close()


@pytest.fixture(scope="module")
def corpus_dir(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("corpus")
    zoning_pdf = tmp / "zoning.pdf"
    make_topic_pdf(
        zoning_pdf,
        "Chapter 110 Zoning",
        "Restaurants require one parking space per 100 square feet of floor area.",
    )
    storm_pdf = tmp / "stormwater.pdf"
    make_topic_pdf(
        storm_pdf,
        "Chapter 200 Stormwater",
        "Detention ponds are required when impervious area increases beyond limits.",
    )
    library = tmp / "library"
    library.mkdir()
    convert(str(zoning_pdf), str(library / "zoning.vera"), model="hashing")
    convert(str(storm_pdf), str(library / "stormwater.vera"), model="hashing")
    return library


class TestOpen:
    def test_discovers_vera_files(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            assert len(corpus.paths) == 2
            assert all(p.endswith(".vera") for p in corpus.paths)

    def test_empty_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            VeraCorpus.open(str(tmp_path))

    def test_empty_directory_can_open_when_explicitly_allowed(self, tmp_path):
        with VeraCorpus.open(str(tmp_path), allow_empty=True) as corpus:
            assert corpus.paths == []
            summary = corpus.inspect_summary()
        assert summary["directory"] == str(tmp_path.resolve())
        assert summary["file_count"] == 0
        assert summary["discovered_file_count"] == 0
        assert summary["summary_source"] == "discovery"
        assert summary["summary_complete"] is False

    def test_non_directory_raises(self, corpus_dir):
        with pytest.raises(NotADirectoryError):
            VeraCorpus.open(str(corpus_dir / "zoning.vera"))


class TestSearch:
    @pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
    def test_attributes_results_to_the_right_file(self, corpus_dir, mode):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            results = corpus.search("restaurant parking space", mode=mode, top_k=3)
            assert results
            top = results[0]
            assert isinstance(top, CorpusSearchResult)
            assert top.file.endswith("zoning.vera")
            assert top.source_filename == "zoning.pdf"
            assert "parking" in top.text.lower()

    def test_results_from_multiple_files(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            results = corpus.search("chapter requirements", mode="hybrid", top_k=10)
            files = {r.file for r in results}
            assert len(files) == 2

    def test_as_dict_includes_file(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            top = corpus.search("detention ponds", top_k=1)[0]
            entry = top.as_dict()
            assert entry["file"].endswith("stormwater.vera")

    def test_context_chunks(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            top = corpus.search("detention ponds", top_k=1, context_chunks=1)[0]
            assert isinstance(top.before_chunks, list)
            assert isinstance(top.after_chunks, list)

    def test_invalid_mode_raises(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            with pytest.raises(ValueError):
                corpus.search("anything", mode="bogus")

    def test_regions_for_corpus_result(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            top = corpus.search("restaurant parking space", top_k=1)[0]
            regions = regions_for(corpus.document(top.file), top)
            assert regions
            assert len(regions[0]["bbox"]) == 4
            assert regions[0]["page_number"] == top.page_start

    def test_fallback_search_skips_malformed_document(self, corpus_dir):
        malformed = corpus_dir / "malformed.vera"
        sqlite3.connect(malformed).close()
        try:
            with VeraCorpus.open(str(corpus_dir), use_index=False) as corpus:
                results = corpus.search("restaurant parking space", top_k=1)
                assert results[0].file.endswith("zoning.vera")
                assert len(corpus.invalid_files) == 1
                assert corpus.invalid_files[0]["file"] == str(malformed.resolve())
                assert "Missing required table: vera_metadata" in corpus.invalid_files[0]["reason"]
        finally:
            malformed.unlink()


class TestInspect:
    def test_summary(self, corpus_dir):
        with VeraCorpus.open(str(corpus_dir)) as corpus:
            info = corpus.inspect()
            assert info["file_count"] == 2
            assert info["pages"] == 2
            assert info["chunks"] >= 2
            assert info["embedding_models"] == ["vera-hashing-384"]
            assert len(info["files"]) == 2

    def test_mixed_library_reports_and_skips_invalid_files(self, corpus_dir):
        malformed = corpus_dir / "malformed.vera"
        sqlite3.connect(malformed).close()
        try:
            with VeraCorpus.open(str(corpus_dir), use_index=False) as corpus:
                info = corpus.inspect()
            assert info["file_count"] == 2
            assert info["discovered_file_count"] == 3
            assert info["skipped"] == 1
            assert info["skipped_files"][0]["file"] == str(malformed.resolve())
            assert "Missing required table: vera_metadata" in info["skipped_files"][0]["reason"]
        finally:
            malformed.unlink()

    def test_summary_without_index_only_discovers_files(self, corpus_dir, monkeypatch):
        def reject_archive_open(path):
            raise AssertionError(f"summary reopened archive: {path}")

        monkeypatch.setattr("vera.corpus.VeraDocument.open", reject_archive_open)
        with VeraCorpus.open(str(corpus_dir), use_index=False) as corpus:
            info = corpus.inspect_summary()

        assert info["summary_source"] == "discovery"
        assert info["summary_complete"] is False
        assert info["file_count"] == 2
        assert info["pages"] is None
        assert info["chunks"] is None


class TestCli:
    def test_search_directory_json(self, corpus_dir):
        proc = subprocess.run(
            [sys.executable, "-m", "vera_cli", "search", str(corpus_dir), "detention ponds", "--top-k", "2", "--json", "--regions"],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        payload = json.loads(proc.stdout)
        first = payload["results"][0]
        assert first["file"].endswith("stormwater.vera")
        assert first["regions"]


@pytest.mark.anyio
async def test_mcp_corpus_search_tool(corpus_dir):
    from vera_mcp import build_server

    server = build_server()
    result = await server.call_tool(
        "vera_corpus_search",
        {"directory": str(corpus_dir), "query": "restaurant parking space", "top_k": 2, "include_regions": True},
    )
    content, structured = result
    payload = structured.get("result", structured) if structured is not None else json.loads(content[0].text)
    first = payload["results"][0]
    assert first["file"].endswith("zoning.vera")
    assert first["regions"]


@pytest.fixture
def anyio_backend():
    return "asyncio"
