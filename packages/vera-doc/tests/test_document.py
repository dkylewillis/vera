"""Unit tests for QueryResult and VeraDocument search/CRUD edge cases."""

import pytest

from vera_doc import ChunkRecord, QueryResult, VeraDocument


class TestQueryResult:
    def _make(self, **kwargs):
        defaults = dict(
            record=ChunkRecord(
                id="c001",
                text="Sample text",
                metadata={"page_start": 1},
            ),
            score=0.85,
        )
        defaults.update(kwargs)
        return QueryResult(**defaults)

    def test_as_dict_contains_all_fields(self):
        r = self._make()
        d = r.as_dict()
        assert d["chunk_id"] == "c001"
        assert d["score"] == pytest.approx(0.85)
        assert d["text"] == "Sample text"
        assert d["metadata"]["page_start"] == 1

    def test_as_dict_is_a_copy(self):
        r = self._make()
        d = r.as_dict()
        d["score"] = 0.0
        assert r.score == pytest.approx(0.85)

    def test_citation_from_metadata(self):
        r = self._make(
            record=ChunkRecord(
                id="c001",
                text="Sample text",
                metadata={
                    "page_start": 12,
                    "page_end": 13,
                    "heading_path": "Chapter 4 > Detention",
                    "source_filename": "manual.pdf",
                    "document_id": "document_0001",
                },
            )
        )
        citation = r.citation
        assert citation.page_start == 12
        assert citation.page_end == 13
        assert citation.heading_path == "Chapter 4 > Detention"
        assert citation.source_filename == "manual.pdf"
        assert citation.document_id == "document_0001"
        assert r.page_start == 12
        assert r.heading_path == "Chapter 4 > Detention"


class TestVeraDocumentSearchValidation:
    def test_invalid_mode_raises_value_error(self, tmp_path):
        path = tmp_path / "test.vera"
        with VeraDocument.create(path) as document:
            document.add([ChunkRecord(id="one", text="hello world")])
            with pytest.raises(ValueError, match="mode must be"):
                document.search(text="query", mode="fuzzy")


class TestVeraDocumentShouldFix:
    def test_creator_library_uses_package_version(self, tmp_path):
        path = tmp_path / "created.vera"
        with VeraDocument.create(path) as document:
            assert document._metadata_values()["creator_library"] == "vera-doc/0.3.1"

    def test_delete_requires_ids_where_or_delete_all(self, tmp_path):
        path = tmp_path / "delete.vera"
        with VeraDocument.create(path) as document:
            document.add([ChunkRecord(id="one", text="hello world")])
            with pytest.raises(ValueError, match="delete_all"):
                document.delete()
            assert document.delete(["one"]) == 1

    def test_delete_all_flag_clears_chunks(self, tmp_path):
        path = tmp_path / "delete-all.vera"
        with VeraDocument.create(path) as document:
            document.add(
                [
                    ChunkRecord(id="one", text="hello world"),
                    ChunkRecord(id="two", text="other text"),
                ]
            )
            assert document.delete(delete_all=True) == 2
            assert document.get() == []

    def test_search_hydrates_only_top_k_records(self, tmp_path):
        path = tmp_path / "topk.vera"
        with VeraDocument.create(path) as document:
            document.add(
                [
                    ChunkRecord(id=f"c{index:02d}", text=f"topic token{index} extra words")
                    for index in range(15)
                ]
            )
            calls: list[list[str] | None] = []
            original = document.get

            def wrapped(ids=None, **kwargs):
                calls.append(list(ids) if ids is not None else None)
                return original(ids, **kwargs)

            document.get = wrapped  # type: ignore[method-assign]
            results = document.search("token3", top_k=3)
            assert len(results) == 3
            assert calls
            assert all(call is not None for call in calls)
            assert all(len(call) <= 3 for call in calls)

    def test_search_rejects_huge_top_k(self, tmp_path):
        path = tmp_path / "limit.vera"
        with VeraDocument.create(path) as document:
            document.add([ChunkRecord(id="one", text="hello world")])
            with pytest.raises(ValueError, match="top_k must be at most"):
                document.search("hello", top_k=10_001)

    def test_keyword_missing_fts_table_is_not_swallowed(self, tmp_path):
        import sqlite3

        path = tmp_path / "fts.vera"
        with VeraDocument.create(path) as document:
            document.add([ChunkRecord(id="one", text="hello world")])
            document._conn.execute("DROP TABLE chunks_fts")
            with pytest.raises(sqlite3.OperationalError):
                document.search("hello", mode="keyword")

    def test_validate_rejects_non_float32_format_and_mixed_dimensions(self, tmp_path):
        import sqlite3

        import numpy as np

        path = tmp_path / "vectors.vera"
        with VeraDocument.create(path) as document:
            document.add([ChunkRecord(id="one", text="hello world")])
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE embeddings SET vector_format = 'float64_le' WHERE chunk_id = 'one'")
        conn.execute(
            """
            INSERT INTO chunks(chunk_id, text, metadata_json, created_at, updated_at)
            VALUES ('two', 'other text', '{}', '', '')
            """
        )
        small = np.zeros(8, dtype="<f4").tobytes()
        conn.execute(
            """
            INSERT INTO embeddings(
                chunk_id, model_name, model_dimension, vector, vector_format, created_at
            ) VALUES ('two', 'vera-hashing-384', 8, ?, 'float32_le', '')
            """,
            (small,),
        )
        conn.execute("INSERT INTO chunks_fts(chunk_id, text) VALUES ('two', 'other text')")
        conn.commit()
        conn.close()
        with VeraDocument.open(path) as document:
            report = document.validate()
        assert report["ok"] is False
        assert any("vector_format" in issue for issue in report["issues"])
        assert any("Mixed embedding dimensions" in issue for issue in report["issues"])
