from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from .schema import (
    FORMAT_VERSION,
    LEGACY_FORMAT_VERSION,
    LEGACY_REQUIRED_METADATA_KEYS,
    REQUIRED_METADATA_KEYS,
)


def validate_document(conn: sqlite3.Connection) -> dict[str, Any]:
    """Validate the VERA container, schema, metadata, indexes, and embeddings."""
    issues: list[str] = []
    warnings: list[str] = []

    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        issues.append(f"SQLite integrity check failed: {integrity}")

    existing_tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','virtual table')"
        )
    }
    metadata = {}
    if "vera_metadata" in existing_tables:
        metadata = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM vera_metadata")
        }
    format_version = metadata.get("format_version")
    modern = format_version == FORMAT_VERSION or (
        {"attachments", "chunk_attachments"}.issubset(existing_tables)
        and "documents" not in existing_tables
    )
    if modern:
        required_tables = {
            "vera_metadata",
            "chunks",
            "embeddings",
            "attachments",
            "chunk_attachments",
            "chunks_fts",
        }
        required_metadata = REQUIRED_METADATA_KEYS
    else:
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
        required_metadata = LEGACY_REQUIRED_METADATA_KEYS
        if format_version not in {LEGACY_FORMAT_VERSION, None}:
            warnings.append(f"Unrecognized format version: {format_version}")
    for table in sorted(required_tables - existing_tables):
        issues.append(f"Missing required table: {table}")

    counts = {
        "documents": _safe_count(conn, "documents", existing_tables),
        "pages": _safe_count(conn, "pages", existing_tables),
        "chunks": _safe_count(conn, "chunks", existing_tables),
        "embeddings": _safe_count(conn, "embeddings", existing_tables),
        "fts_rows": _safe_count(conn, "chunks_fts", existing_tables),
        "assets": _safe_count(
            conn,
            "attachments" if modern else "assets",
            existing_tables,
        ),
    }

    if "vera_metadata" in existing_tables:
        for key in required_metadata:
            if key not in metadata:
                issues.append(f"Missing required metadata key: {key}")

    if not modern:
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
    if modern and "attachments" in existing_tables:
        original_document_present = (
            conn.execute(
                """
                SELECT COUNT(*) FROM attachments
                WHERE json_extract(metadata_json, '$.role') = 'source'
                """
            ).fetchone()[0]
            > 0
        )
        archive_metadata: dict[str, Any] = {}
        try:
            parsed_archive_metadata = json.loads(
                metadata.get("archive_metadata", "{}")
            )
            if isinstance(parsed_archive_metadata, dict):
                archive_metadata = parsed_archive_metadata
        except json.JSONDecodeError:
            pass
        if (
            not original_document_present
            and archive_metadata.get("source_file_name")
        ):
            warnings.append("Original document asset is missing")
    elif "assets" in existing_tables:
        original_document_present = (
            conn.execute("SELECT COUNT(*) FROM assets WHERE asset_type='original_document'").fetchone()[0] > 0
        )
        if not original_document_present:
            warnings.append("Original document asset is missing")

    if "embeddings" in existing_tables:
        embedding_id = "chunk_id" if modern else "embedding_id"
        for row in conn.execute(
            f"SELECT {embedding_id}, chunk_id, model_dimension, vector "
            f"FROM embeddings ORDER BY {embedding_id}"
        ):
            expected = int(row["model_dimension"] or 0) * 4
            actual = len(row["vector"] or b"")
            if expected <= 0 or actual != expected:
                issues.append(
                    f"Invalid embedding blob for {row[embedding_id]} / {row['chunk_id']}: expected {expected} bytes, got {actual}"
                )

    if modern:
        foreign_key_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_issues:
            issues.append(
                f"Foreign key violations found: {len(foreign_key_issues)}"
            )
        if "chunks" in existing_tables:
            for row in conn.execute(
                "SELECT chunk_id, text, metadata_json FROM chunks"
            ):
                if not str(row["text"] or "").strip():
                    issues.append(f"Chunk {row['chunk_id']} has empty text")
                _validate_json_object(
                    row["metadata_json"],
                    f"chunk {row['chunk_id']} metadata",
                    issues,
                )
        if "attachments" in existing_tables:
            for row in conn.execute(
                "SELECT attachment_id, data, hash, metadata_json FROM attachments"
            ):
                digest = hashlib.sha256(bytes(row["data"] or b"")).hexdigest()
                if row["hash"] != digest:
                    issues.append(
                        f"Attachment {row['attachment_id']} checksum mismatch"
                    )
                _validate_json_object(
                    row["metadata_json"],
                    f"attachment {row['attachment_id']} metadata",
                    issues,
                )
        if "archive_metadata" in metadata:
            _validate_json_object(
                metadata["archive_metadata"],
                "archive metadata",
                issues,
            )

    if not modern and "chunks" in existing_tables and "pages" in existing_tables:
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


def _validate_json_object(
    value: str,
    label: str,
    issues: list[str],
) -> None:
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        issues.append(f"Invalid JSON in {label}")
        return
    if not isinstance(parsed, dict):
        issues.append(f"{label.capitalize()} must be a JSON object")
