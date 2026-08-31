"""Build, update, and status reporting for persistent library indexes."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import numpy as np

from ._index_layout import (
    INDEX_DATABASE,
    INDEX_DIRECTORY,
    INDEX_GENERATIONS,
    INDEX_POINTER,
    INDEX_VERSION,
    _database_path,
    _gc_index_generations,
    _generation_path,
    _index_build_lock,
    _index_path,
    _path_size,
    _relative,
    _sha256_file,
    discover_vera_files,
)
from ._util import _utc_now
from .document import VeraDocument
from .embeddings import deserialize_vector
from .models import (
    METADATA_DOCUMENT_ID,
    METADATA_HEADING_PATH,
    METADATA_PAGE_END,
    METADATA_PAGE_START,
    METADATA_SOURCE_FILENAME,
    metadata_from_json,
    thaw_json,
)


def _create_index_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;
        CREATE TABLE index_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE files (
            file_id INTEGER PRIMARY KEY,
            relative_path TEXT NOT NULL UNIQUE,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            source_hash TEXT,
            source_filename TEXT,
            title TEXT,
            created_at TEXT,
            metadata_json TEXT NOT NULL
        );
        CREATE TABLE skipped_files (
            relative_path TEXT PRIMARY KEY,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            category TEXT NOT NULL,
            reason TEXT NOT NULL
        );
        CREATE TABLE chunks (
            row_id INTEGER PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
            chunk_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            vector_row INTEGER NOT NULL,
            text TEXT NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            heading_path TEXT,
            source_filename TEXT,
            UNIQUE(file_id, chunk_id)
        );
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            row_id UNINDEXED,
            text,
            heading_path,
            source_filename
        );
        CREATE TABLE vector_groups (
            model_name TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            filename TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            PRIMARY KEY(model_name, dimension)
        );
        CREATE INDEX idx_chunks_vector_row
            ON chunks(model_name, dimension, vector_row);
        CREATE INDEX idx_chunks_file ON chunks(file_id);
        """
    )


def _group_filename(model_name: str, dimension: int) -> str:
    digest = hashlib.sha256(f"{model_name}\0{dimension}".encode()).hexdigest()[:16]
    return f"vectors-{digest}-{dimension}.npy"


def _read_existing_files(root: Path) -> dict[str, dict[str, Any]]:
    database = _database_path(root)
    if not database.is_file():
        return {}
    try:
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        try:
            return {row["relative_path"]: dict(row) for row in conn.execute("SELECT * FROM files")}
        finally:
            conn.close()
    except sqlite3.Error:
        return {}


def _change_summary(
    old_files: dict[str, dict[str, Any]],
    new_files: dict[str, dict[str, Any]],
) -> dict[str, int]:
    old_paths = set(old_files)
    new_paths = set(new_files)
    added_paths = new_paths - old_paths
    removed_paths = old_paths - new_paths
    changed = sum(
        old_files[path].get("content_hash") != new_files[path].get("content_hash")
        for path in old_paths & new_paths
    )
    old_hash_paths: dict[str, set[str]] = {}
    for path in removed_paths:
        old_hash_paths.setdefault(old_files[path].get("content_hash", ""), set()).add(path)
    moved = 0
    for path in list(added_paths):
        digest = new_files[path].get("content_hash", "")
        if digest and old_hash_paths.get(digest):
            moved += 1
            old_hash_paths[digest].pop()
    return {
        "added": max(0, len(added_paths) - moved),
        "changed": changed,
        "moved": moved,
        "removed": max(0, len(removed_paths) - moved),
    }


def build_library_index(
    directory: str,
    *,
    recursive: bool = False,
    excludes: Iterable[str] = (),
    includes: Iterable[str] = (),
    operation: str = "build",
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build an index atomically and return a machine-readable report.

    ``progress`` receives factual phase updates with per-file counts. Callers
    can surface these updates without inspecting an index while it is being
    assembled.
    """
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(directory)
    exclude_patterns = tuple(dict.fromkeys(str(pattern) for pattern in excludes))
    include_patterns = tuple(dict.fromkeys(str(pattern) for pattern in includes))
    if progress:
        progress(
            {
                "phase": "discovering",
                "completed": 0,
                "total": 0,
                "input": str(root),
                "chunks": 0,
                "skipped": 0,
            }
        )
    paths = discover_vera_files(
        root,
        recursive=recursive,
        excludes=exclude_patterns,
        includes=include_patterns,
    )
    if not paths:
        raise FileNotFoundError(f"No .vera files found in {directory}")
    if progress:
        progress(
            {
                "phase": "indexing",
                "completed": 0,
                "total": len(paths),
                "input": "",
                "chunks": 0,
                "skipped": 0,
            }
        )

    old_files = _read_existing_files(root)
    target = _index_path(root)
    generation_name = f"generation-{uuid.uuid4().hex}"
    temporary = root / f"{INDEX_DIRECTORY}.build-{uuid.uuid4().hex}"
    temporary.mkdir()
    conn = sqlite3.connect(temporary / INDEX_DATABASE)
    conn.row_factory = sqlite3.Row
    vectors: dict[tuple[str, int], list[np.ndarray]] = {}
    invalid: list[dict[str, str]] = []
    incompatible: list[dict[str, str]] = []
    indexed_files = 0
    indexed_chunks = 0
    source_chunks = 0
    processed_files = 0

    def record_skipped(path: Path, relative_path: str, category: str, reason: str) -> None:
        try:
            stat = path.stat()
            conn.execute(
                """
                INSERT OR REPLACE INTO skipped_files(
                    relative_path, size, mtime_ns, category, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (relative_path, stat.st_size, stat.st_mtime_ns, category, reason),
            )
        except OSError:
            pass

    try:
        _create_index_schema(conn)
        config = {
            "root": str(root),
            "recursive": recursive,
            "excludes": list(exclude_patterns),
            "includes": list(include_patterns),
            "index_version": INDEX_VERSION,
        }
        metadata = {
            "index_version": str(INDEX_VERSION),
            "created_at": _utc_now(),
            "config": json.dumps(config, sort_keys=True),
        }
        conn.executemany("INSERT INTO index_metadata(key, value) VALUES (?, ?)", metadata.items())

        for path in paths:
            relative_path = _relative(path, root)
            if progress:
                progress(
                    {
                        "phase": "indexing",
                        "completed": processed_files,
                        "total": len(paths),
                        "input": relative_path,
                        "chunks": indexed_chunks,
                        "skipped": processed_files - indexed_files,
                    }
                )
            vector_lengths = {group: len(values) for group, values in vectors.items()}
            conn.execute("SAVEPOINT index_file")
            try:
                doc = VeraDocument.open(str(path))
                try:
                    validation = doc.validate()
                    if not validation["ok"]:
                        reason = "; ".join(validation["issues"])
                        invalid.append({"file": relative_path, "reason": reason})
                        record_skipped(path, relative_path, "invalid", reason)
                        conn.execute("RELEASE SAVEPOINT index_file")
                        continue
                    stored_metadata = doc.format_metadata()
                    archive_metadata = doc.metadata
                    file_metadata = {**stored_metadata, **archive_metadata}
                    file_metadata["_vera_page_count"] = int(archive_metadata.get("page_count", 0))
                    document = {
                        "source_filename": archive_metadata.get("source_file_name"),
                        "title": archive_metadata.get("title"),
                        "created_at": stored_metadata.get("created_at"),
                    }
                    modern_rows = list(doc.iter_raw_chunks())
                    file_source_chunks = len(modern_rows)
                    rows = []
                    for modern_row in modern_rows:
                        chunk_metadata = thaw_json(metadata_from_json(modern_row["metadata_json"]))
                        rows.append(
                            {
                                **modern_row,
                                "document_id": chunk_metadata.get(
                                    METADATA_DOCUMENT_ID,
                                    "document_0001",
                                ),
                                "page_start": chunk_metadata.get(METADATA_PAGE_START),
                                "page_end": chunk_metadata.get(METADATA_PAGE_END),
                                "heading_path": chunk_metadata.get(METADATA_HEADING_PATH),
                                "source_filename": chunk_metadata.get(
                                    METADATA_SOURCE_FILENAME,
                                    archive_metadata.get("source_file_name"),
                                ),
                            }
                        )
                    prepared: list[tuple[Any, np.ndarray, tuple[str, int]]] = []
                    file_problem = None
                    for row in rows:
                        dimension = int(row["model_dimension"])
                        vector = deserialize_vector(row["vector"])
                        if vector.size != dimension:
                            file_problem = (
                                f"{row['chunk_id']} has {vector.size} values; expected {dimension}"
                            )
                            break
                        group = (str(row["model_name"]), dimension)
                        prepared.append((row, vector, group))
                    if file_problem:
                        incompatible.append({"file": relative_path, "reason": file_problem})
                        record_skipped(path, relative_path, "incompatible", file_problem)
                        conn.execute("RELEASE SAVEPOINT index_file")
                        continue

                    stat = path.stat()
                    cursor = conn.execute(
                        """
                        INSERT INTO files(
                            relative_path, size, mtime_ns, content_hash, source_hash,
                            source_filename, title, created_at, metadata_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            relative_path,
                            stat.st_size,
                            stat.st_mtime_ns,
                            _sha256_file(path),
                            file_metadata.get("source_file_hash"),
                            document["source_filename"]
                            if document
                            else file_metadata.get("source_file_name"),
                            document["title"] if document else None,
                            document["created_at"] if document else file_metadata.get("created_at"),
                            json.dumps(file_metadata, sort_keys=True),
                        ),
                    )
                    file_id = int(cursor.lastrowid or 0)
                    for row, vector, group in prepared:
                        vector_row = len(vectors.setdefault(group, []))
                        norm = float(np.linalg.norm(vector))
                        normalized = (
                            (vector / norm).astype(np.float32)
                            if norm
                            else vector.astype(np.float32)
                        )
                        vectors[group].append(normalized)
                        chunk_cursor = conn.execute(
                            """
                            INSERT INTO chunks(
                                file_id, chunk_id, document_id, model_name, dimension,
                                vector_row, text, page_start, page_end, heading_path,
                                source_filename
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                file_id,
                                row["chunk_id"],
                                row["document_id"],
                                group[0],
                                group[1],
                                vector_row,
                                row["text"],
                                row["page_start"],
                                row["page_end"],
                                row["heading_path"],
                                row["source_filename"],
                            ),
                        )
                        conn.execute(
                            "INSERT INTO chunks_fts(row_id, text, heading_path, source_filename) VALUES (?, ?, ?, ?)",
                            (
                                int(chunk_cursor.lastrowid or 0),
                                row["text"],
                                row["heading_path"],
                                row["source_filename"],
                            ),
                        )
                finally:
                    doc.close()
                conn.execute("RELEASE SAVEPOINT index_file")
                indexed_files += 1
                indexed_chunks += len(prepared)
                source_chunks += file_source_chunks
            except Exception as exc:
                conn.execute("ROLLBACK TO SAVEPOINT index_file")
                conn.execute("RELEASE SAVEPOINT index_file")
                for group in list(vectors):
                    if group in vector_lengths:
                        del vectors[group][vector_lengths[group] :]
                    else:
                        del vectors[group]
                reason = str(exc)
                invalid.append({"file": relative_path, "reason": reason})
                record_skipped(path, relative_path, "invalid", reason)
            finally:
                processed_files += 1
                if progress:
                    progress(
                        {
                            "phase": "indexing",
                            "completed": processed_files,
                            "total": len(paths),
                            "input": relative_path,
                            "chunks": indexed_chunks,
                            "skipped": processed_files - indexed_files,
                        }
                    )

        if not indexed_files:
            raise ValueError("No valid .vera files could be indexed")
        if progress:
            progress(
                {
                    "phase": "finalizing",
                    "completed": processed_files,
                    "total": len(paths),
                    "input": "",
                    "chunks": indexed_chunks,
                    "skipped": processed_files - indexed_files,
                }
            )

        for (model_name, dimension), group_vectors in vectors.items():
            filename = _group_filename(model_name, dimension)
            matrix = np.vstack(group_vectors).astype(np.float32, copy=False)
            np.save(temporary / filename, matrix, allow_pickle=False)
            conn.execute(
                "INSERT INTO vector_groups(model_name, dimension, filename, row_count) VALUES (?, ?, ?, ?)",
                (model_name, dimension, filename, matrix.shape[0]),
            )
        conn.executemany(
            "INSERT INTO index_metadata(key, value) VALUES (?, ?)",
            (
                ("source_chunks", str(source_chunks)),
                ("indexed_chunks", str(indexed_chunks)),
            ),
        )
        conn.commit()
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"Index integrity check failed: {check}")
    except Exception:
        conn.close()
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    else:
        conn.close()

    generation_path = target / INDEX_GENERATIONS / generation_name
    pointer_temporary = target / f"{INDEX_POINTER}.tmp-{uuid.uuid4().hex}"
    try:
        with _index_build_lock(target):
            (target / INDEX_GENERATIONS).mkdir(parents=True, exist_ok=True)
            temporary.rename(generation_path)
            pointer_temporary.write_text(
                json.dumps(
                    {
                        "generation": generation_name,
                        "index_version": INDEX_VERSION,
                        "created_at": metadata["created_at"],
                    }
                ),
                encoding="utf-8",
            )
            os.replace(pointer_temporary, target / INDEX_POINTER)
            _gc_index_generations(target, generation_name)
    except Exception:
        pointer_temporary.unlink(missing_ok=True)
        shutil.rmtree(temporary, ignore_errors=True)
        shutil.rmtree(generation_path, ignore_errors=True)
        raise

    new_files = _read_existing_files(root)
    changes = _change_summary(old_files, new_files)
    return {
        "ok": True,
        "operation": operation,
        "directory": str(root),
        "index": str(target),
        "generation_id": generation_name,
        "created_at": metadata["created_at"],
        "recursive": recursive,
        "excludes": list(exclude_patterns),
        "includes": list(include_patterns),
        "discovered": len(paths),
        "indexed": indexed_files,
        "chunks": indexed_chunks,
        "skipped": len(paths) - indexed_files,
        "invalid": invalid,
        "incompatible": incompatible,
        **changes,
    }


def _load_config(root: Path) -> dict[str, Any] | None:
    database = _database_path(root)
    if not database.is_file():
        return None
    try:
        conn = sqlite3.connect(database)
        try:
            row = conn.execute("SELECT value FROM index_metadata WHERE key = 'config'").fetchone()
            return json.loads(row[0]) if row else None
        finally:
            conn.close()
    except (sqlite3.Error, json.JSONDecodeError, OSError):
        return None


def update_library_index(
    directory: str,
    *,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Rebuild an existing library index using its persisted discovery settings."""
    root = Path(directory).resolve()
    config = _load_config(root)
    if config is None:
        raise FileNotFoundError(
            f"No library index found in {directory}; run 'vera index build' first"
        )
    return build_library_index(
        str(root),
        recursive=bool(config.get("recursive", False)),
        excludes=config.get("excludes", ()),
        includes=config.get("includes", ()),
        operation="update",
        progress=progress,
    )


def library_index_status(directory: str, *, verify_hashes: bool = True) -> dict[str, Any]:
    """Report whether a library index exists and matches the current file tree."""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(directory)
    database = _database_path(root)
    if not database.is_file():
        return {
            "directory": str(root),
            "index": str(_index_path(root)),
            "exists": False,
            "fresh": False,
            "reasons": ["index is missing"],
            "skipped_files": [],
        }
    config = _load_config(root)
    if config is None:
        return {
            "directory": str(root),
            "index": str(_index_path(root)),
            "exists": True,
            "fresh": False,
            "reasons": ["index configuration is unreadable"],
            "skipped_files": [],
        }
    reasons: list[str] = []
    try:
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        try:
            index_metadata = {
                str(row["key"]): str(row["value"])
                for row in conn.execute("SELECT key, value FROM index_metadata")
            }
            version_value = index_metadata.get("index_version")
            if version_value is None or int(version_value) != INDEX_VERSION:
                reasons.append("index version is unsupported")
            indexed = {
                row["relative_path"]: dict(row) for row in conn.execute("SELECT * FROM files")
            }
            skipped = {
                row["relative_path"]: dict(row)
                for row in conn.execute("SELECT * FROM skipped_files")
            }
            groups = list(conn.execute("SELECT * FROM vector_groups"))
            model_groups = [
                {
                    "model": str(row["model_name"]),
                    "dimension": int(row["dimension"]),
                    "documents": int(row["document_count"]),
                    "chunks": int(row["chunk_count"]),
                    "vector_file": str(row["filename"]),
                }
                for row in conn.execute(
                    """
                    SELECT
                        c.model_name,
                        c.dimension,
                        COUNT(DISTINCT c.file_id) AS document_count,
                        COUNT(c.row_id) AS chunk_count,
                        vg.filename
                    FROM chunks c
                    JOIN vector_groups vg
                      ON vg.model_name = c.model_name
                     AND vg.dimension = c.dimension
                    GROUP BY c.model_name, c.dimension, vg.filename
                    ORDER BY c.model_name, c.dimension
                    """
                )
            ]
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                reasons.append("index database integrity check failed")
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, OSError) as exc:
        reasons.append(f"index database is unreadable: {exc}")
        indexed = {}
        skipped = {}
        groups = []
        model_groups = []
        index_metadata = {}

    discovered = discover_vera_files(
        root,
        recursive=bool(config.get("recursive", False)),
        excludes=config.get("excludes", ()),
        includes=config.get("includes", ()),
    )
    current_paths = {_relative(path, root): path for path in discovered}
    indexed_paths = set(indexed) | set(skipped)
    if set(current_paths) != indexed_paths:
        reasons.append("library files were added, removed, or moved")
    for relative_path in set(current_paths) & indexed_paths:
        try:
            stat = current_paths[relative_path].stat()
            row = indexed.get(relative_path) or skipped[relative_path]
            if stat.st_size != row["size"] or stat.st_mtime_ns != row["mtime_ns"]:
                reasons.append(f"file changed: {relative_path}")
            elif verify_hashes and relative_path in indexed:
                if _sha256_file(current_paths[relative_path]) != row["content_hash"]:
                    reasons.append(f"file content changed: {relative_path}")
        except OSError as exc:
            reasons.append(f"file is unreadable: {relative_path}: {exc}")
    for group in groups:
        vector_path = _generation_path(root) / group["filename"]
        if not vector_path.is_file():
            reasons.append(f"vector matrix is missing: {group['filename']}")
            continue
        try:
            matrix = np.load(vector_path, mmap_mode="r", allow_pickle=False)
            if matrix.shape != (group["row_count"], group["dimension"]):
                reasons.append(f"vector matrix shape is invalid: {group['filename']}")
        except (OSError, ValueError):
            reasons.append(f"vector matrix is unreadable: {group['filename']}")
    generation = _generation_path(root)
    for group in model_groups:
        vector_file = generation / str(group["vector_file"])
        group["vector_size_bytes"] = vector_file.stat().st_size if vector_file.is_file() else 0
    database_size = database.stat().st_size if database.is_file() else 0
    vector_size = sum(
        (generation / str(group["filename"])).stat().st_size
        for group in groups
        if (generation / str(group["filename"])).is_file()
    )
    indexed_chunks = sum(int(str(group["chunks"])) for group in model_groups)
    source_chunks = int(index_metadata.get("source_chunks", indexed_chunks))
    checked_at = _utc_now()
    return {
        "directory": str(root),
        "index": str(_index_path(root)),
        "exists": True,
        "fresh": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "generation_id": generation.name if generation.parent.name == INDEX_GENERATIONS else None,
        "created_at": index_metadata.get("created_at"),
        "checked_at": checked_at,
        "verified_at": checked_at if verify_hashes else None,
        "index_size_bytes": _path_size(generation),
        "database_size_bytes": database_size,
        "vector_size_bytes": vector_size,
        "recursive": bool(config.get("recursive", False)),
        "excludes": list(config.get("excludes", ())),
        "includes": list(config.get("includes", ())),
        "file_count": len(indexed),
        "skipped": len(skipped),
        "skipped_files": [
            {
                "file": relative_path,
                "category": row["category"],
                "reason": row["reason"],
            }
            for relative_path, row in sorted(skipped.items())
        ],
        "discovered": len(discovered),
        "indexed_chunks": indexed_chunks,
        "source_chunks": source_chunks,
        "model_groups": model_groups,
    }
