"""SQLite FTS5 helpers shared by archive search and the collection index."""

from __future__ import annotations

import sqlite3
from typing import Any

_FTS_RUNTIME_MARKERS = (
    "database is locked",
    "database disk image is malformed",
    "no such table",
    "no such module",
    "unable to open database",
    "disk i/o error",
    "attempt to write a readonly",
    "locking protocol",
)


def is_fts_syntax_error(exc: BaseException) -> bool:
    """Return True when ``exc`` is an FTS query-syntax failure, not a runtime error."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    message = str(exc).lower()
    if any(marker in message for marker in _FTS_RUNTIME_MARKERS):
        return False
    return True


def safe_fts_query(raw: str) -> str:
    """Return an OR-joined prefix query, or empty when no safe tokens remain."""
    terms = []
    for token in raw.split():
        cleaned = "".join(
            character for character in token if character.isalnum() or character == "_"
        )
        if cleaned:
            terms.append(f"{cleaned}*")
    return " OR ".join(terms)


def execute_fts(
    conn: sqlite3.Connection,
    sql: str,
    query: str,
    *params: Any,
) -> list[sqlite3.Row]:
    """Run an FTS MATCH query; syntax errors become empty hits, other errors raise."""
    try:
        return conn.execute(sql, (query, *params)).fetchall()
    except sqlite3.OperationalError as exc:
        if not is_fts_syntax_error(exc):
            raise
        return []
