"""FTS5 query sanitization and syntax-vs-runtime error handling."""

from __future__ import annotations

import sqlite3

import pytest

from vera_doc import ChunkRecord, VeraDocument
from vera_doc.document import execute_fts, is_fts_syntax_error, safe_fts_query


def test_safe_fts_query_prefixes_alnum_tokens_and_drops_punctuation() -> None:
    assert safe_fts_query("storm-water detention!") == "stormwater* OR detention*"
    assert safe_fts_query("section_4_2") == "section_4_2*"
    assert safe_fts_query('""') == ""
    assert safe_fts_query("   ") == ""
    assert safe_fts_query("!!! ???") == ""


def test_is_fts_syntax_error_excludes_runtime_markers() -> None:
    assert is_fts_syntax_error(sqlite3.OperationalError('fts5: syntax error near "'))
    assert is_fts_syntax_error(sqlite3.OperationalError('unrecognized token: "'))
    assert not is_fts_syntax_error(sqlite3.OperationalError("database is locked"))
    assert not is_fts_syntax_error(sqlite3.OperationalError("no such table: chunks_fts"))
    assert not is_fts_syntax_error(sqlite3.OperationalError("database disk image is malformed"))
    assert not is_fts_syntax_error(ValueError('fts5: syntax error near "'))


def test_execute_fts_forwards_extra_params_and_swallows_syntax() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE VIRTUAL TABLE docs USING fts5(text)")
    conn.execute("INSERT INTO docs(text) VALUES ('stormwater detention pond')")
    conn.execute("INSERT INTO docs(text) VALUES ('landscaping guidance')")

    sql = "SELECT text FROM docs WHERE docs MATCH ? AND text LIKE ? ORDER BY rank LIMIT ?"
    rows = execute_fts(conn, sql, "detention", "%pond%", 5)
    assert [row["text"] for row in rows] == ["stormwater detention pond"]

    assert execute_fts(conn, "SELECT text FROM docs WHERE docs MATCH ?", '"unbalanced') == []

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        execute_fts(conn, "SELECT text FROM missing WHERE missing MATCH ?", "detention")
    conn.close()


def test_keyword_search_recovers_from_unbalanced_quotes(tmp_path) -> None:
    path = tmp_path / "fts.vera"
    with VeraDocument.create(path) as document:
        document.add(
            [
                ChunkRecord(
                    id="chunk_0001",
                    text="Stormwater detention pond requirements.",
                    metadata={"page_start": 1, "page_end": 1},
                )
            ]
        )
        hits = document.search('"detention', mode="keyword", top_k=3)
        assert hits
        assert "detention" in hits[0].text.lower()
        assert document.search("!!!", mode="keyword", top_k=3) == []
