from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import numpy as np

from .schema import FORMAT_VERSION, REQUIRED_METADATA_KEYS

_EMBEDDING_NORMALIZATIONS = {"l2", "none", "unknown"}
_L2_NORMALIZATION_RTOL = 1e-4
_L2_NORMALIZATION_ATOL = 1e-6


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
    required_tables = {
        "vera_metadata",
        "chunks",
        "embeddings",
        "attachments",
        "chunk_attachments",
        "chunks_fts",
    }
    if format_version != FORMAT_VERSION:
        issues.append(
            f"Unsupported format version: {format_version or 'missing'} "
            f"(expected {FORMAT_VERSION})"
        )
    for table in sorted(required_tables - existing_tables):
        issues.append(f"Missing required table: {table}")

    counts = {
        "chunks": _safe_count(conn, "chunks", existing_tables),
        "embeddings": _safe_count(conn, "embeddings", existing_tables),
        "fts_rows": _safe_count(conn, "chunks_fts", existing_tables),
        "attachments": _safe_count(conn, "attachments", existing_tables),
    }

    if "vera_metadata" in existing_tables:
        for key in REQUIRED_METADATA_KEYS:
            if key not in metadata:
                issues.append(f"Missing required metadata key: {key}")
        embedding_normalization = metadata.get(
            "default_embedding_normalization", "unknown"
        )
        if embedding_normalization not in _EMBEDDING_NORMALIZATIONS:
            issues.append(
                "Invalid default_embedding_normalization: "
                f"{embedding_normalization!r}"
            )
    else:
        embedding_normalization = "unknown"

    if counts["embeddings"] != counts["chunks"]:
        issues.append(f"Embedding count ({counts['embeddings']}) does not match chunk count ({counts['chunks']})")
    if counts["fts_rows"] != counts["chunks"]:
        issues.append(f"FTS row count ({counts['fts_rows']}) does not match chunk count ({counts['chunks']})")

    original_document_present = False
    if "attachments" in existing_tables:
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
    if "embeddings" in existing_tables:
        dimensions: set[int] = set()
        try:
            declared_dimension = int(
                metadata.get("default_embedding_dimension") or 0
            )
        except (TypeError, ValueError):
            declared_dimension = 0
        for row in conn.execute(
            "SELECT chunk_id, model_dimension, vector, vector_format "
            "FROM embeddings ORDER BY chunk_id"
        ):
            vector_format = row["vector_format"]
            if vector_format != "float32_le":
                issues.append(
                    f"Unsupported vector_format for {row['chunk_id']}: "
                    f"{vector_format!r} (expected 'float32_le')"
                )
            dimension = int(row["model_dimension"] or 0)
            dimensions.add(dimension)
            expected = dimension * 4
            actual = len(row["vector"] or b"")
            if expected <= 0 or actual != expected:
                issues.append(
                    f"Invalid embedding blob for {row['chunk_id']}: expected {expected} bytes, got {actual}"
                )
                continue
            vector = np.frombuffer(row["vector"], dtype="<f4")
            if not np.isfinite(vector).all():
                issues.append(
                    f"Embedding vector for {row['chunk_id']} contains non-finite values"
                )
                continue
            norm = float(np.linalg.norm(vector))
            if (
                embedding_normalization == "l2"
                and norm != 0.0
                and not np.isclose(
                    norm,
                    1.0,
                    rtol=_L2_NORMALIZATION_RTOL,
                    atol=_L2_NORMALIZATION_ATOL,
                )
            ):
                issues.append(
                    f"Embedding vector for {row['chunk_id']} is not L2-normalized "
                    f"(norm {norm:.8g})"
                )
        if len(dimensions) > 1:
            issues.append(
                f"Mixed embedding dimensions in one archive: {sorted(dimensions)}"
            )
        elif (
            declared_dimension
            and dimensions
            and dimensions != {declared_dimension}
        ):
            issues.append(
                "Embedding dimensions "
                f"{sorted(dimensions)} do not match default_embedding_dimension "
                f"{declared_dimension}"
            )

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
