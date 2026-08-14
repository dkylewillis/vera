"""Tests for recursive discovery and the rebuildable local collection index."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from helpers.pdfs import make_topic_pdf
from vera_doc import (
    VeraCorpus,
    VeraDocument,
    build_library_index,
    library_index_status,
    update_library_index,
)
from vera_doc.collection import discover_vera_files
from vera_ingest import convert
from vera_ingest.viewer import regions_for


def _sequence_library(tmp_path, n_pages: int = 12, target_index: int = 5):
    """Build a library whose middle page is uniquely searchable with neighbors."""
    import fitz

    library = tmp_path / "seq-library"
    library.mkdir()
    pdf = tmp_path / "sequence.pdf"
    doc = fitz.open()
    before_text = "Alpha approach overview precedes the target section."
    after_text = "Omega followup details come after the target section."
    for index in range(n_pages):
        page = doc.new_page()
        if index == target_index:
            text = "Middle Target\nBeacon target language lives in this middle section."
        elif index == target_index - 1:
            text = f"Opening Context\n{before_text}"
        elif index == target_index + 1:
            text = f"Closing Context\n{after_text}"
        else:
            text = f"Filler {index:02d}\nUnique filler token filler_{index:02d} padding text."
        page.insert_text((72, 72), text)
    doc.save(pdf)
    doc.close()
    vera = library / "sequence.vera"
    convert(str(pdf), str(vera), model="hashing", chunk_size=100, overlap=0)
    with VeraDocument.open(str(vera)) as archive:
        records = list(archive.get())
    hit_index = next(
        index for index, record in enumerate(records) if "beacon target" in record.text.lower()
    )
    return library, len(records), records[hit_index - 1].text, records[hit_index + 1].text


def _spy_document_get_ids(monkeypatch):
    """Record every VeraDocument.get(ids=...) call; None means a full-table load."""
    calls: list[list[str] | None] = []
    original = VeraDocument.get

    def spy(self, ids=None, *, where=None, limit=None):
        calls.append(None if ids is None else list(ids))
        return original(self, ids, where=where, limit=limit)

    monkeypatch.setattr(VeraDocument, "get", spy)
    return calls


def _convert_topic(
    root: Path,
    relative: str,
    heading: str,
    body: str,
    *,
    model: str = "hashing",
    embedding_function=None,
) -> Path:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    pdf = target.with_suffix(".pdf")
    make_topic_pdf(pdf, heading, body)
    convert(str(pdf), str(target), model=model, embedding_function=embedding_function)
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
        with VeraCorpus.open(
            str(nested_library), recursive=True, excludes=["archive"], use_index=False
        ) as corpus:
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
        with VeraCorpus.open(
            str(nested_library), recursive=True, excludes=["archive"], use_index=False
        ) as corpus:
            with pytest.raises(ValueError, match="top_k"):
                corpus.search("roadway", top_k=-1)
            with pytest.raises(ValueError, match="context_chunks"):
                corpus.search("roadway", context_chunks=-1)


class TestBuildAndSearch:
    def test_reports_factual_progress_through_index_publication(self, nested_library):
        events = []

        report = build_library_index(
            str(nested_library),
            recursive=True,
            excludes=["archive"],
            progress=events.append,
        )

        assert events[0] == {
            "phase": "discovering",
            "completed": 0,
            "total": 0,
            "input": str(nested_library.resolve()),
            "chunks": 0,
            "skipped": 0,
        }
        indexing = [event for event in events if event["phase"] == "indexing"]
        assert [event["completed"] for event in indexing] == [0, 0, 1, 1, 2]
        assert indexing[-1]["total"] == report["discovered"] == 2
        assert indexing[-1]["chunks"] == report["chunks"]
        assert indexing[-1]["skipped"] == 0
        assert events[-1] == {
            "phase": "finalizing",
            "completed": 2,
            "total": 2,
            "input": "",
            "chunks": report["chunks"],
            "skipped": 0,
        }

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
        assert status["generation_id"].startswith("generation-")
        assert status["created_at"]
        assert status["checked_at"]
        assert status["verified_at"] == status["checked_at"]
        assert status["index_size_bytes"] > 0
        assert status["database_size_bytes"] > 0
        assert status["vector_size_bytes"] > 0
        assert status["indexed_chunks"] == report["chunks"]
        assert status["source_chunks"] >= status["indexed_chunks"]
        assert status["model_groups"] == [
            {
                "model": "vera-hashing-384",
                "dimension": 384,
                "documents": 2,
                "chunks": report["chunks"],
                "vector_file": status["model_groups"][0]["vector_file"],
                "vector_size_bytes": status["model_groups"][0]["vector_size_bytes"],
            }
        ]
        assert status["model_groups"][0]["vector_size_bytes"] > 0

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
            assert regions_for(corpus.document(result.file), result)

    def test_context_chunks_hydrates_neighbors_without_full_table(self, tmp_path, monkeypatch):
        library, chunk_count, before_text, after_text = _sequence_library(tmp_path)
        build_library_index(str(library))
        fetched_ids = _spy_document_get_ids(monkeypatch)

        with VeraCorpus.open(str(library)) as corpus:
            assert corpus.uses_index is True
            result = corpus.search(
                "beacon target",
                mode="keyword",
                top_k=1,
                context_chunks=1,
            )[0]

        assert "beacon target" in result.text.lower()
        assert len(result.before_chunks) == 1
        assert len(result.after_chunks) == 1
        assert before_text.lower() in result.before_chunks[0]["text"].lower()
        assert after_text.lower() in result.after_chunks[0]["text"].lower()
        payload = result.as_dict()
        assert "before_chunks" in payload
        assert "after_chunks" in payload
        # Regression: hydration must pass explicit ids to get(), never the full table.
        assert fetched_ids
        assert all(ids is not None for ids in fetched_ids)
        assert max(len(ids) for ids in fetched_ids) < chunk_count

    def test_indexed_summary_does_not_reopen_archives(self, nested_library, monkeypatch):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])

        def reject_archive_open(path):
            raise AssertionError(f"summary reopened archive: {path}")

        monkeypatch.setattr(VeraDocument, "open", staticmethod(reject_archive_open))
        with VeraCorpus.open(str(nested_library)) as corpus:
            summary = corpus.inspect_summary()

        assert summary["summary_source"] == "index"
        assert summary["summary_complete"] is True
        assert summary["file_count"] == 2
        assert summary["pages"] == 2
        assert summary["chunks"] >= 2
        assert summary["embedding_models"] == ["vera-hashing-384"]
        assert len(summary["files"]) == 2

    def test_mixed_embedding_models_are_rank_fused(self, tmp_path):
        from vera_doc.embeddings import HashingEmbedder, register_embedder, unregister_embedder

        def alternate_factory(model_id: str, **config):
            return HashingEmbedder(model_name=f"alternate:{model_id or 'default'}")

        register_embedder("alternate", alternate_factory, replace=True)
        try:
            root = tmp_path / "mixed"
            _convert_topic(
                root,
                "one.vera",
                "Road Design",
                "Roadway design project experience.",
                model="hashing",
            )
            _convert_topic(
                root,
                "two.vera",
                "Road Planning",
                "Roadway planning project experience.",
                model="alternate:default",
            )
            report = build_library_index(str(root))
            assert report["indexed"] == 2
            status = library_index_status(str(root))
            assert {
                (group["model"], group["dimension"], group["documents"])
                for group in status["model_groups"]
            } == {
                ("alternate:default", 384, 1),
                ("vera-hashing-384", 384, 1),
            }
            with VeraCorpus.open(str(root)) as corpus:
                results = corpus.search("roadway project experience", mode="semantic", top_k=2)
                assert {Path(result.file).name for result in results} == {"one.vera", "two.vera"}
            with VeraCorpus.open(str(root), use_index=False) as corpus:
                results = corpus.search("roadway project experience", mode="semantic", top_k=2)
                assert {Path(result.file).name for result in results} == {"one.vera", "two.vera"}
        finally:
            unregister_embedder("alternate")

    def test_unavailable_semantic_model_does_not_break_keyword_search(
        self, nested_library, monkeypatch
    ):
        import vera_doc.collection as collection

        build_library_index(str(nested_library), recursive=True, excludes=["archive"])

        def unavailable(model):
            raise ImportError(model)

        monkeypatch.setattr(collection, "get_embedder", unavailable)
        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus.search("water treatment", mode="semantic") == []
            assert corpus.skipped_semantic_model_groups == [
                {
                    "model_name": "vera-hashing-384",
                    "dimension": 384,
                    "error": "ImportError: vera-hashing-384",
                }
            ]
            assert corpus.search("water treatment", mode="hybrid")[0].file.endswith("water.vera")
            assert (
                corpus.skipped_semantic_model_groups[0]["error"] == "ImportError: vera-hashing-384"
            )
            assert corpus.search("water treatment", mode="keyword")[0].file.endswith("water.vera")
            assert corpus.skipped_semantic_model_groups == []

    def test_unknown_registered_model_is_skipped_at_query_time(self, tmp_path):
        from vera_doc.embeddings import HashingEmbedder, register_embedder, unregister_embedder

        def factory(model_id: str, **config):
            return HashingEmbedder(model_name=f"ephemeral:{model_id or 'default'}")

        register_embedder("ephemeral", factory, replace=True)
        try:
            root = tmp_path / "ephemeral"
            _convert_topic(
                root,
                "doc.vera",
                "Water Treatment",
                "Municipal water treatment pumping improvements.",
                model="ephemeral:default",
            )
            build_library_index(str(root))
        finally:
            unregister_embedder("ephemeral")

        with VeraCorpus.open(str(root)) as corpus:
            assert corpus.search("water treatment", mode="semantic") == []
            assert len(corpus.skipped_semantic_model_groups) == 1
            skipped = corpus.skipped_semantic_model_groups[0]
            assert skipped["model_name"] == "ephemeral:default"
            assert skipped["dimension"] == 384
            assert "UnknownEmbeddingModelError" in skipped["error"]
            assert corpus.search("water treatment", mode="keyword")[0].file.endswith("doc.vera")

    def test_incompatible_runtime_model_dimension_is_reported(self, nested_library, monkeypatch):
        import vera_doc.collection as collection

        build_library_index(str(nested_library), recursive=True, excludes=["archive"])

        class WrongDimensionEmbedder:
            dimension = 768

        monkeypatch.setattr(collection, "get_embedder", lambda model: WrongDimensionEmbedder())
        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus.search("water treatment", mode="semantic") == []
            assert corpus.skipped_semantic_model_groups == [
                {
                    "model_name": "vera-hashing-384",
                    "dimension": 384,
                    "error": "Runtime model dimension 768 does not match indexed dimension 384",
                }
            ]

    def test_invalid_files_are_reported_without_making_index_stale(
        self, nested_library, monkeypatch
    ):
        invalid = nested_library / "broken.vera"
        invalid.write_text("not sqlite", encoding="utf-8")
        report = build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        assert report["invalid"][0]["file"] == "broken.vera"
        status = library_index_status(str(nested_library))
        assert status["fresh"] is True
        assert status["skipped"] == 1
        assert status["skipped_files"][0]["file"] == "broken.vera"
        assert status["skipped_files"][0]["category"] == "invalid"

        original_open = VeraDocument.open

        def reject_skipped(path):
            if Path(path).resolve() == invalid.resolve():
                raise AssertionError("indexed skipped file should not be opened")
            return original_open(path)

        monkeypatch.setattr(VeraDocument, "open", staticmethod(reject_skipped))
        with VeraCorpus.open(str(nested_library)) as corpus:
            info = corpus.inspect()
        assert info["file_count"] == 2
        assert info["skipped"] == 1
        assert info["skipped_files"][0]["file"] == str(invalid.resolve())

    def test_punctuation_only_keyword_query_returns_no_results(self, nested_library):
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        with VeraCorpus.open(str(nested_library)) as corpus:
            assert corpus.search("!!!", mode="keyword") == []

    def test_hybrid_index_and_fanout_share_chunk_order(self, nested_library):
        query = "municipal water treatment pumping"
        build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        with VeraCorpus.open(str(nested_library)) as indexed:
            assert indexed.uses_index is True
            indexed_keys = [
                (Path(result.file).name, result.chunk_id)
                for result in indexed.search(query, mode="hybrid", top_k=5)
            ]
        with VeraCorpus.open(
            str(nested_library),
            recursive=True,
            excludes=["archive"],
            use_index=False,
        ) as fanout:
            assert fanout.uses_index is False
            fanout_keys = [
                (Path(result.file).name, result.chunk_id)
                for result in fanout.search(query, mode="hybrid", top_k=5)
            ]
        assert indexed_keys
        assert indexed_keys == fanout_keys

    def test_rebuild_garbage_collects_old_generations(self, nested_library):
        from vera_doc.collection import INDEX_DIRECTORY, INDEX_GENERATIONS

        first = build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        second = build_library_index(str(nested_library), recursive=True, excludes=["archive"])
        generations = nested_library / INDEX_DIRECTORY / INDEX_GENERATIONS
        remaining = [path.name for path in generations.iterdir() if path.is_dir()]
        assert remaining == [second["generation_id"]]
        assert first["generation_id"] not in remaining


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
        import vera_doc.collection as collection

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
        assert searched["skipped_semantic_model_groups"] == []
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
    from vera_mcp import build_server

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
    payload = (
        structured.get("result", structured)
        if structured is not None
        else json.loads(content[0].text)
    )
    assert payload["results"][0]["file"].endswith("roadway.vera")
    assert "figures" in payload["results"][0]
    assert payload["index"]["used"] is False


@pytest.mark.anyio
async def test_mcp_reports_skipped_semantic_model_groups(nested_library, monkeypatch):
    import vera_doc.collection as collection
    from vera_mcp import build_server

    build_library_index(str(nested_library), recursive=True, excludes=["archive"])

    def unavailable(model):
        raise ImportError(f"{model} dependency is unavailable")

    monkeypatch.setattr(collection, "get_embedder", unavailable)
    result = await build_server().call_tool(
        "vera_corpus_search",
        {
            "directory": str(nested_library),
            "query": "water treatment",
            "mode": "hybrid",
            "top_k": 1,
        },
    )
    content, structured = result
    payload = (
        structured.get("result", structured)
        if structured is not None
        else json.loads(content[0].text)
    )
    assert payload["results"][0]["file"].endswith("water.vera")
    assert payload["skipped_semantic_model_groups"] == [
        {
            "model_name": "vera-hashing-384",
            "dimension": 384,
            "error": "ImportError: vera-hashing-384 dependency is unavailable",
        }
    ]


@pytest.fixture
def anyio_backend():
    return "asyncio"
