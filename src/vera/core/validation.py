from __future__ import annotations

import sqlite3
from typing import Any

from ..schema import REQUIRED_METADATA_KEYS


def validate_document(conn: sqlite3.Connection) -> dict[str, Any]:
    """Validate the VERA container, schema, metadata, indexes, and embeddings."""
    issues: list[str] = []
    warnings: list[str] = []
    required_tables = {
        "vera_metadata",
        "documents",
        "pages",
        "blocks",
        "chunks",
        "chunk_blocks",
        "embeddings",
        "assets",
        "chunks_fts",
    }

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        issues.append(f"SQLite integrity check failed: {integrity}")

    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
        )
    }
    for table in sorted(required_tables - existing_tables):
        issues.append(f"Missing required table: {table}")

    counts = {
        "documents": _safe_count(conn, "documents", existing_tables),
        "pages": _safe_count(conn, "pages", existing_tables),
        "chunks": _safe_count(conn, "chunks", existing_tables),
        "embeddings": _safe_count(conn, "embeddings", existing_tables),
        "fts_rows": _safe_count(conn, "chunks_fts", existing_tables),
        "assets": _safe_count(conn, "assets", existing_tables),
    }

    metadata = {}
    if "vera_metadata" in existing_tables:
        metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM vera_metadata")}
        for key in REQUIRED_METADATA_KEYS:
            if key not in metadata:
                issues.append(f"Missing required metadata key: {key}")

    if counts["documents"] < 1:
        issues.append("No document records found")
    if counts["pages"] < 1:
        issues.append("No page records found")
    if counts["chunks"] < 1:
        issues.append("No chunks found")
    if counts["embeddings"] != counts["chunks"]:
        issues.append(f"Embedding count ({counts['embeddings']}) does not match chunk count ({counts['chunks']})")
    if counts["fts_rows"] != counts["chunks"]:
        issues.append(f"FTS row count ({counts['fts_rows']}) does not match chunk count ({counts['chunks']})")

    original_document_present = False
    if "assets" in existing_tables:
        original_document_present = (
            conn.execute("SELECT COUNT(*) FROM assets WHERE asset_type='original_document'").fetchone()[0] > 0
        )
        if not original_document_present:
            issues.append("Original document asset is missing")

    if "embeddings" in existing_tables:
        for row in conn.execute(
            "SELECT embedding_id, chunk_id, model_dimension, vector FROM embeddings ORDER BY embedding_id"
        ):
            expected = int(row["model_dimension"] or 0) * 4
            actual = len(row["vector"] or b"")
            if expected <= 0 or actual != expected:
                issues.append(
                    f"Invalid embedding blob for {row['embedding_id']} / {row['chunk_id']}: expected {expected} bytes, got {actual}"
                )

    if "chunks" in existing_tables and "pages" in existing_tables:
        bad_page_refs = conn.execute(
            """
            SELECT COUNT(*) FROM chunks
            WHERE page_start IS NOT NULL
              AND page_start NOT IN (SELECT page_number FROM pages)
            """
        ).fetchone()[0]
        if bad_page_refs:
            issues.append(f"Chunks with invalid page_start references: {bad_page_refs}")

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "counts": counts,
        "checks": {
            "sqlite_integrity": integrity,
            "required_tables_present": required_tables.issubset(existing_tables),
            "original_document_present": original_document_present,
        },
        "metadata": metadata,
    }


def _safe_count(conn: sqlite3.Connection, table: str, existing_tables: set[str]) -> int:
    if table not in existing_tables:
        return 0
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
