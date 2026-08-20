"""Keyword FTS sanitization: syntax errors must not look like empty libraries."""

from __future__ import annotations

import sqlite3

import pytest

from vera_doc import ChunkRecord, VeraDocument
from vera_doc._fts import execute_fts, is_fts_syntax_error, safe_fts_query


def _fts_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id, text)")
    conn.execute("INSERT INTO chunks_fts(chunk_id, text) VALUES ('one', 'stormwater detention')")
    conn.execute("INSERT INTO chunks_fts(chunk_id, text) VALUES ('two', 'parking stall count')")
    return conn


class TestSafeFtsQuery:
    def test_builds_or_joined_prefix_terms(self):
        assert safe_fts_query("stormwater detention") == "stormwater* OR detention*"

    def test_strips_operators_and_quotes(self):
        assert safe_fts_query('detention AND "basin"') == "detention* OR AND* OR basin*"

    def test_keeps_underscores(self):
        assert safe_fts_query("chunk_0042") == "chunk_0042*"

    def test_punctuation_only_is_empty(self):
        assert safe_fts_query('!!! "()"') == ""


class TestFtsSyntaxVsRuntime:
    def test_syntax_errors_are_swallowed_as_empty_hits(self):
        conn = _fts_conn()
        rows = execute_fts(
            conn,
            "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?",
            'detention "',
        )
        assert rows == []

    def test_runtime_errors_are_not_treated_as_syntax(self):
        conn = _fts_conn()
        conn.execute("DROP TABLE chunks_fts")
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            execute_fts(
                conn,
                "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?",
                "detention",
            )

    def test_locked_and_malformed_markers_are_runtime(self):
        for message in (
            "database is locked",
            "database disk image is malformed",
            "no such table: chunks_fts",
            "no such module: fts5",
            "unable to open database file",
            "disk I/O error",
            "attempt to write a readonly database",
            "locking protocol",
        ):
            assert is_fts_syntax_error(sqlite3.OperationalError(message)) is False

    def test_generic_fts_syntax_is_recoverable(self):
        assert is_fts_syntax_error(sqlite3.OperationalError('fts5: syntax error near "')) is True
        assert is_fts_syntax_error(ValueError("fts5: syntax error")) is False

    def test_extra_sql_params_are_forwarded(self):
        conn = _fts_conn()
        rows = execute_fts(
            conn,
            "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT ?",
            "detention",
            1,
        )
        assert [row["chunk_id"] for row in rows] == ["one"]


def test_keyword_search_recovers_from_unbalanced_fts_quotes(tmp_path):
    path = tmp_path / "manual.vera"
    with VeraDocument.create(path) as document:
        document.add(
            [
                ChunkRecord(
                    id="one",
                    text="Stormwater detention basin volume requirements.",
                    metadata={"page_start": 12},
                )
            ]
        )
        results = document.search('detention "', mode="keyword", top_k=5)
        assert results
        assert "detention" in results[0].text.lower()
        assert results[0].page_start == 12
