"""Tests for recursive discovery and the rebuildable local collection index."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from vera import VeraCorpus, VeraDocument, build_library_index, convert, library_index_status, update_library_index
from vera.collection import INDEX_DIRECTORY, discover_vera_files
from test_corpus import make_topic_pdf


def _convert_topic(root: Path, relative: str, heading: str, body: str, *, model: str = "hashing") -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = target.with_suffix(".pdf")
    make_topic_pdf(pdf, heading, body)
    convert(str(pdf), str(target), model=model)
    return target


@pytest.fixture
def nested_library(tmp_path):
    root = tmp_path / "proposals"
    _convert_topic(
        root,
        "transportation/2024/roadway.vera",
        "Roadway Design",
        "Our team delivered roadway corridor design and construction administration.",
    )
    _convert_topic(
        root,
        "utilities/2023/water.vera",
        "Water Treatment",
        "Our team designed municipal water treatment and pumping improvements.",
    )
    _convert_topic(
        root,
        "archive/old.vera",
        "Archived Work",
        "This archived proposal should be excluded from the active library.",
    )
    return root


class TestDiscovery:
    def test_opening_missing_document_does_not_create_it(self, tmp_path):
        missing = tmp_path / "missing.vera"
        with pytest.raises(FileNotFoundError):
            VeraDocument.open(str(missing))
        assert not missing.exists()

    def test_recursive_is_opt_in(self, nested_library):
        assert discover_vera_files(nested_library) == []
        recursive = discover_vera_files(nested_library, recursive=True)
        assert len(recursive) == 3

    def test_exclusions_match_directory_names(self, nested_library):
        recursive = discover_vera_files(nested_library, recursive=True, excludes=["archive"])
        assert len(recursive) == 2
        assert all("archive" not in path.parts for path in recursive)

    def test_corpus_can_search_nested_files_without_an_index(self, nested_library):
        with VeraCorpus.open(str(nested_library), recursive=True, excludes=["archive"], use_index=False) as corpus:
            results = corpus.search("water treatment pumping", top_k=2)
            assert results
            assert results[0].file.endswith("water.vera")
            assert corpus._collection_index is None

    def test_document_cache_is_bounded(self, nested_library):
        with VeraCorpus.open(
            str(nested_library),
            recursive=True,
            excludes=["archive"],
            max_open_documents=1,
            use_index=False,
        ) as corpus:
            corpus.document(corpus.paths[0])
            corpus.document(corpus.paths[1])
            assert len(corpus._docs) == 1
            assert next(iter(corpus._docs)) == corpus.paths[1]

    def test_rejects_negative_search_limits(self, nested_library):
        with VeraCorpus.open(str(nested_library), recursive=True, excludes=["archive"], use_index=False) as corpus:
            with pytest.raises(ValueError, match="top_k"):
                corpus.search("roadway", top_k=-1)
            with pytest.raises(ValueError, match="context_chunks"):
                corpus.search("roadway", context_chunks=-1)


class TestBuildAndSearch:
    def test_builds_fresh_index_and_searches_it_automatically(self, nested_library):
        report = build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        assert report["ok"] is True
        assert report["discovered"] == 2
        assert report["indexed"] == 2
        assert report["chunks"] >= 2

        status = library_index_status(str(nested_library))
        assert status["fresh"] is True
        assert status["recursive"] is True
        assert status["excludes"] == ["archive"]

        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus.uses_index is True
            results = corpus.search("roadway corridor construction", top_k=2)
            assert results[0].file.endswith("roadway.vera")
            assert "roadway" in results[0].text.lower()
            assert results[0].page_start == 1

    @pytest.mark.parametrize("mode", ["keyword", "semantic", "hybrid"])
    def test_index_supports_all_search_modes(self, nested_library, mode):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        with VeraCorpus.open(str(nested_library)) as corpus:
            result = corpus.search("municipal water treatment", mode=mode, top_k=1)[0]
            assert result.file.endswith("water.vera")

    def test_context_and_regions_resolve_from_source_vera(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        with VeraCorpus.open(str(nested_library)) as corpus:
            result = corpus.search("water treatment pumping", top_k=1, context_chunks=1)[0]
            assert isinstance(result.before_chunks, list)
            assert isinstance(result.after_chunks, list)
            assert corpus.regions_for(result)

    def test_mixed_embedding_models_are_rank_fused(self, tmp_path):
        root = tmp_path / "mixed"
        _convert_topic(root, "one.vera", "Road Design", "Roadway design project experience.", model="hashing")
        _convert_topic(root, "two.vera", "Road Planning", "Roadway planning project experience.", model="alternate-model")
        report = build_library_index(str(root))
        assert report["indexed"] == 2
        with VeraCorpus.open(str(root)) as corpus:
            results = corpus.search("roadway project experience", mode="semantic", top_k=2)
            assert {Path(result.file).name for result in results} == {"one.vera", "two.vera"}
        with VeraCorpus.open(str(root), use_index=False) as corpus:
            results = corpus.search("roadway project experience", mode="semantic", top_k=2)
            assert {Path(result.file).name for result in results} == {"one.vera", "two.vera"}

    def test_unavailable_semantic_model_does_not_break_keyword_search(self, nested_library, monkeypatch):
        import vera.collection as collection

        build_library_index(str(nested_library), recursive=True, excludes=["archive"])

        def unavailable(model):
            raise ImportError(model)

        monkeypatch.setattr(collection, "get_embedder", unavailable)
        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus.search("water treatment", mode="semantic") == []
            assert corpus.search("water treatment", mode="keyword")[0].file.endswith("water.vera")

    def test_invalid_files_are_reported_without_making_index_stale(self, nested_library):
        invalid = nested_library / "broken.vera"
        invalid.write_text("not sqlite", encoding="utf-8")
        report = build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        assert report["invalid"][0]["file"] == "broken.vera"
        status = library_index_status(str(nested_library))
        assert status["fresh"] is True
        assert status["skipped"] == 1

    def test_punctuation_only_keyword_query_returns_no_results(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus.search("!!!", mode="keyword") == []


class TestUpdatesAndFallback:
    def test_stale_index_falls_back_to_recursive_fanout(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        _convert_topic(
            nested_library,
            "environmental/2025/wetlands.vera",
            "Wetland Permitting",
            "Wetland delineation and environmental permitting services.",
        )
        status = library_index_status(str(nested_library))
        assert status["fresh"] is False

        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus._collection_index is None
            result = corpus.search("wetland delineation permitting", top_k=1)[0]
            assert result.file.endswith("wetlands.vera")

    def test_update_detects_add_change_move_and_remove(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        roadway = nested_library / "transportation/2024/roadway.vera"
        moved = nested_library / "transportation/roadway-moved.vera"
        moved.parent.mkdir(parents=True, exist_ok=True)
        roadway.rename(moved)
        (nested_library / "utilities/2023/water.vera").unlink()
        _convert_topic(
            nested_library,
            "environmental/new.vera",
            "Environmental",
            "Environmental review and permitting.",
        )

        report = update_library_index(str(nested_library))
        assert report["moved"] == 1
        assert report["removed"] == 1
        assert report["added"] == 1
        assert library_index_status(str(nested_library))["fresh"] is True

    def test_update_detects_changed_file(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        _convert_topic(
            nested_library,
            "utilities/2023/water.vera",
            "Water Treatment",
            "Updated membrane filtration and municipal pumping improvements.",
        )
        report = update_library_index(str(nested_library))
        assert report["changed"] == 1
        assert report["added"] == 0
        assert report["removed"] == 0

    def test_full_status_hash_check_catches_same_stat_change(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        path = nested_library / "utilities/2023/water.vera"
        stat = path.stat()
        conn = sqlite3.connect(path)
        try:
            conn.execute("UPDATE vera_metadata SET value = 'test' WHERE key = 'created_by'")
            conn.commit()
        finally:
            conn.close()
        assert path.stat().st_size == stat.st_size
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        status = library_index_status(str(nested_library))
        assert status["fresh"] is False
        assert any("content changed" in reason for reason in status["reasons"])

    def test_failed_rebuild_preserves_previous_index(self, nested_library, monkeypatch):
        import vera.collection as collection

        build_library_index(str(nested_library), recursive=True, excludes=["archive"])

        def fail_save(*args, **kwargs):
            raise OSError("simulated vector write failure")

        monkeypatch.setattr(collection.np, "save", fail_save)
        with pytest.raises(OSError, match="simulated"):
            build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        assert library_index_status(str(nested_library))["fresh"] is True

    def test_update_can_publish_while_previous_generation_is_open(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        with VeraCorpus.open(str(nested_library)) as old_corpus:
            assert old_corpus.search("water treatment", top_k=1)
            report = update_library_index(str(nested_library))
            assert report["ok"] is True
            assert old_corpus.search("roadway corridor", top_k=1)
        assert library_index_status(str(nested_library))["fresh"] is True


class TestCli:
    def _run_json(self, *args: str, check: bool = True) -> dict:
        proc = subprocess.run(
            [sys.executable, "-m", "vera_cli", *args],
            text=True,
            capture_output=True,
            check=check,
        )
        return json.loads(proc.stdout)

    def test_index_build_status_update_and_search(self, nested_library):
        built = self._run_json(
            "index",
            "build",
            str(nested_library),
            "--recursive",
            "--exclude",
            "archive",
            "--json",
        )
        assert built["indexed"] == 2
        status = self._run_json("index", "status", str(nested_library), "--json")
        assert status["fresh"] is True
        searched = self._run_json(
            "search",
            str(nested_library),
            "water treatment",
            "--top-k",
            "1",
            "--json",
        )
        assert searched["results"][0]["file"].endswith("water.vera")
        assert searched["index"]["used"] is True
        updated = self._run_json("index", "update", str(nested_library), "--json")
        assert updated["indexed"] == 2

    def test_recursive_search_flag_works_without_index(self, nested_library):
        searched = self._run_json(
            "search",
            str(nested_library),
            "roadway corridor",
            "--recursive",
            "--exclude",
            "archive",
            "--top-k",
            "1",
            "--json",
        )
        assert searched["results"][0]["file"].endswith("roadway.vera")


@pytest.mark.anyio
async def test_mcp_recursive_corpus_search(nested_library):
    from vera.integrations.mcp_server import build_server

    server = build_server()
    result = await server.call_tool(
        "vera_corpus_search",
        {
            "directory": str(nested_library),
            "query": "roadway corridor",
            "recursive": True,
            "excludes": ["archive"],
            "include_figures": True,
            "top_k": 1,
        },
    )
    content, structured = result
    payload = structured.get("result", structured) if structured is not None else json.loads(content[0].text)
    assert payload["results"][0]["file"].endswith("roadway.vera")
    assert "figures" in payload["results"][0]
    assert payload["index"]["used"] is False


@pytest.fixture
def anyio_backend():
    return "asyncio"
