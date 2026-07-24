"""Rebuildable library-level search index for collections of .vera files."""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .core.embeddings import deserialize_vector, get_embedder
from .document import VeraDocument

INDEX_DIRECTORY = ".vera-index"
INDEX_DATABASE = "index.sqlite3"
INDEX_POINTER = "current.json"
INDEX_GENERATIONS = "generations"
INDEX_VERSION = 1
_RRF_K = 60.0


@dataclass(frozen=True)
class IndexHit:
    """A ranked index hit that can be resolved against its source .vera file."""

    relative_path: str
    chunk_id: str
    score: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _index_path(root: Path) -> Path:
    return root / INDEX_DIRECTORY


def _generation_path(root: Path) -> Path:
    index_root = _index_path(root)
    pointer = index_root / INDEX_POINTER
    if pointer.is_file():
        try:
            generation = json.loads(pointer.read_text(encoding="utf-8"))["generation"]
            if not isinstance(generation, str) or Path(generation).name != generation:
                raise ValueError("invalid generation")
            return index_root / INDEX_GENERATIONS / generation
        except (OSError, ValueError, KeyError, json.JSONDecodeError, TypeError):
            return index_root / "__invalid_generation__"
    return index_root


def _database_path(root: Path) -> Path:
    return _generation_path(root) / INDEX_DATABASE


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _excluded(relative_path: str, excludes: tuple[str, ...]) -> bool:
    parts = relative_path.split("/")
    for pattern in excludes:
        normalized = pattern.replace("\\", "/").strip("/")
        if not normalized:
            continue
        if fnmatch.fnmatch(relative_path, normalized):
            return True
        if any(fnmatch.fnmatch(part, normalized) for part in parts):
            return True
        if normalized.endswith("/**") and relative_path.startswith(normalized[:-3].rstrip("/") + "/"):
            return True
    return False


def discover_vera_files(
    directory: str | Path,
    *,
    recursive: bool = False,
    excludes: Iterable[str] = (),
) -> list[Path]:
    """Discover unique .vera files without following directory symlinks."""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(directory))
    patterns = tuple(excludes)
    if recursive:
        candidates: list[Path] = []
        for current, directories, filenames in os.walk(root, followlinks=False):
            current_path = Path(current)
            kept_directories = []
            for name in directories:
                child = current_path / name
                relative_child = _relative(child, root)
                if child.is_symlink() or _excluded(relative_child, patterns):
                    continue
                kept_directories.append(name)
            directories[:] = kept_directories
            candidates.extend(current_path / name for name in filenames if name.lower().endswith(".vera"))
    else:
        candidates = [path for path in root.iterdir() if path.suffix.lower() == ".vera"]
    discovered: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            if not candidate.is_file() or candidate.is_symlink():
                continue
            relative_path = _relative(candidate, root)
            if _excluded(relative_path, patterns):
                continue
            resolved = candidate.resolve()
            key = os.path.normcase(str(resolved))
            if key in seen:
                continue
            seen.add(key)
            discovered.append(resolved)
        except (OSError, ValueError):
            continue
    return sorted(discovered, key=lambda path: _relative(path, root).lower())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


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
    digest = hashlib.sha256(f"{model_name}\0{dimension}".encode("utf-8")).hexdigest()[:16]
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
    operation: str = "build",
) -> dict[str, Any]:
    """Build an index atomically and return a machine-readable report."""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise NotADirectoryError(directory)
    exclude_patterns = tuple(dict.fromkeys(str(pattern) for pattern in excludes))
    paths = discover_vera_files(root, recursive=recursive, excludes=exclude_patterns)
    if not paths:
        raise FileNotFoundError(f"No .vera files found in {directory}")

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
                    file_metadata = {
                        row["key"]: row["value"]
                        for row in doc.conn.execute("SELECT key, value FROM vera_metadata")
                    }
                    document = doc.conn.execute("SELECT * FROM documents ORDER BY rowid LIMIT 1").fetchone()
                    rows = doc.conn.execute(
                        """
                        SELECT c.*, d.source_filename, e.model_name, e.model_dimension, e.vector
                        FROM chunks c
                        JOIN documents d ON d.document_id = c.document_id
                        JOIN embeddings e ON e.chunk_id = c.chunk_id
                        ORDER BY c.sort_order
                        """
                    ).fetchall()
                    prepared: list[tuple[sqlite3.Row, np.ndarray, tuple[str, int]]] = []
                    file_problem = None
                    for row in rows:
                        dimension = int(row["model_dimension"])
                        vector = deserialize_vector(row["vector"])
                        if vector.size != dimension:
                            file_problem = f"{row['chunk_id']} has {vector.size} values; expected {dimension}"
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
                            document["source_filename"] if document else file_metadata.get("source_file_name"),
                            document["title"] if document else None,
                            document["created_at"] if document else file_metadata.get("created_at"),
                            json.dumps(file_metadata, sort_keys=True),
                        ),
                    )
                    file_id = int(cursor.lastrowid)
                    for row, vector, group in prepared:
                        vector_row = len(vectors.setdefault(group, []))
                        norm = float(np.linalg.norm(vector))
                        normalized = (vector / norm).astype(np.float32) if norm else vector.astype(np.float32)
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
                            (int(chunk_cursor.lastrowid), row["text"], row["heading_path"], row["source_filename"]),
                        )
                finally:
                    doc.close()
                conn.execute("RELEASE SAVEPOINT index_file")
                indexed_files += 1
                indexed_chunks += len(prepared)
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

        if not indexed_files:
            raise ValueError("No valid .vera files could be indexed")

        for (model_name, dimension), group_vectors in vectors.items():
            filename = _group_filename(model_name, dimension)
            matrix = np.vstack(group_vectors).astype(np.float32, copy=False)
            np.save(temporary / filename, matrix, allow_pickle=False)
            conn.execute(
                "INSERT INTO vector_groups(model_name, dimension, filename, row_count) VALUES (?, ?, ?, ?)",
                (model_name, dimension, filename, matrix.shape[0]),
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
        (target / INDEX_GENERATIONS).mkdir(parents=True, exist_ok=True)
        temporary.rename(generation_path)
        pointer_temporary.write_text(
            json.dumps({"generation": generation_name, "index_version": INDEX_VERSION}),
            encoding="utf-8",
        )
        os.replace(pointer_temporary, target / INDEX_POINTER)
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
        "recursive": recursive,
        "excludes": list(exclude_patterns),
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


def update_library_index(directory: str) -> dict[str, Any]:
    """Rebuild an existing library index using its persisted discovery settings."""
    root = Path(directory).resolve()
    config = _load_config(root)
    if config is None:
        raise FileNotFoundError(f"No library index found in {directory}; run 'vera index build' first")
    return build_library_index(
        str(root),
        recursive=bool(config.get("recursive", False)),
        excludes=config.get("excludes", ()),
        operation="update",
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
        }
    config = _load_config(root)
    if config is None:
        return {
            "directory": str(root),
            "index": str(_index_path(root)),
            "exists": True,
            "fresh": False,
            "reasons": ["index configuration is unreadable"],
        }
    reasons: list[str] = []
    try:
        conn = sqlite3.connect(database)
        conn.row_factory = sqlite3.Row
        try:
            version_row = conn.execute("SELECT value FROM index_metadata WHERE key = 'index_version'").fetchone()
            if version_row is None or int(version_row["value"]) != INDEX_VERSION:
                reasons.append("index version is unsupported")
            indexed = {row["relative_path"]: row for row in conn.execute("SELECT * FROM files")}
            skipped = {row["relative_path"]: row for row in conn.execute("SELECT * FROM skipped_files")}
            groups = list(conn.execute("SELECT * FROM vector_groups"))
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                reasons.append("index database integrity check failed")
        finally:
            conn.close()
    except (sqlite3.Error, ValueError, OSError) as exc:
        reasons.append(f"index database is unreadable: {exc}")
        indexed = {}
        skipped = {}
        groups = []

    discovered = discover_vera_files(
        root,
        recursive=bool(config.get("recursive", False)),
        excludes=config.get("excludes", ()),
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
    return {
        "directory": str(root),
        "index": str(_index_path(root)),
        "exists": True,
        "fresh": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "recursive": bool(config.get("recursive", False)),
        "excludes": list(config.get("excludes", ())),
        "file_count": len(indexed),
        "skipped": len(skipped),
        "discovered": len(discovered),
    }


def _safe_fts_query(raw: str) -> str:
    terms = []
    for token in raw.split():
        cleaned = "".join(ch for ch in token if ch.isalnum() or ch == "_")
        if cleaned:
            terms.append(f"{cleaned}*")
    return " OR ".join(terms)


class VeraCollectionIndex:
    """Opened local collection index used by VeraCorpus when it is fresh."""

    def __init__(self, root: Path, generation: Path, conn: sqlite3.Connection):
        self.root = root
        self.generation = generation
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._matrices: dict[str, np.ndarray] = {}

    @classmethod
    def open(cls, directory: str, *, check_status: bool = True) -> "VeraCollectionIndex":
        root = Path(directory).resolve()
        if check_status:
            status = library_index_status(str(root), verify_hashes=False)
            if not status["fresh"]:
                raise ValueError("; ".join(status["reasons"]))
        generation = _generation_path(root)
        return cls(root, generation, sqlite3.connect(generation / INDEX_DATABASE))

    def close(self) -> None:
        self._matrices.clear()
        self.conn.close()

    def __enter__(self) -> "VeraCollectionIndex":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _matrix(self, filename: str) -> np.ndarray:
        if filename not in self._matrices:
            self._matrices[filename] = np.load(
                self.generation / filename,
                mmap_mode="r",
                allow_pickle=False,
            )
        return self._matrices[filename]

    def _semantic_hits(self, query: str, limit: int) -> list[tuple[int, float]]:
        per_group: list[list[tuple[int, float]]] = []
        for group in self.conn.execute("SELECT * FROM vector_groups ORDER BY model_name, dimension"):
            try:
                embedder = get_embedder(group["model_name"])
                if embedder.dimension != group["dimension"]:
                    continue
                query_vector = np.asarray(embedder.embed([query])[0], dtype=np.float32)
            except Exception:
                # Keyword search remains available when a recorded model cannot
                # be loaded in the current environment.
                continue
            norm = float(np.linalg.norm(query_vector))
            if norm:
                query_vector /= norm
            matrix = self._matrix(group["filename"])
            scores = np.asarray(matrix @ query_vector)
            take = min(limit, scores.size)
            if take == 0:
                continue
            if take == scores.size:
                positions = np.argsort(scores)[::-1]
            else:
                positions = np.argpartition(scores, -take)[-take:]
                positions = positions[np.argsort(scores[positions])[::-1]]
            vector_rows = [int(position) for position in positions]
            placeholders = ",".join("?" for _ in vector_rows)
            rows = self.conn.execute(
                f"""
                SELECT row_id, vector_row FROM chunks
                WHERE model_name = ? AND dimension = ?
                  AND vector_row IN ({placeholders})
                """,
                (group["model_name"], group["dimension"], *vector_rows),
            ).fetchall()
            row_ids = {int(row["vector_row"]): int(row["row_id"]) for row in rows}
            per_group.append(
                [(row_ids[position], float(scores[position])) for position in vector_rows if position in row_ids]
            )
        if not per_group:
            return []
        if len(per_group) == 1:
            return per_group[0][:limit]
        fused = [
            (row_id, 1.0 / (_RRF_K + rank))
            for group_hits in per_group
            for rank, (row_id, _) in enumerate(group_hits, start=1)
        ]
        return sorted(fused, key=lambda item: item[1], reverse=True)[:limit]

    def _keyword_hits(self, query: str, limit: int) -> list[tuple[int, float]]:
        sql = """
            SELECT row_id, bm25(chunks_fts) AS rank
            FROM chunks_fts WHERE chunks_fts MATCH ?
            ORDER BY rank LIMIT ?
        """
        try:
            rows = self.conn.execute(sql, (query, limit)).fetchall()
        except sqlite3.OperationalError:
            rows = []
        if not rows:
            fallback = _safe_fts_query(query)
            if not fallback:
                return []
            try:
                rows = self.conn.execute(sql, (fallback, limit)).fetchall()
            except sqlite3.OperationalError:
                return []
        hits = []
        for row in rows:
            rank = float(row["rank"])
            score = 1.0 / (1.0 + max(rank, 0.0)) if rank >= 0 else 1.0 + abs(rank)
            hits.append((int(row["row_id"]), score))
        return hits

    def search(self, query: str, mode: str = "hybrid", top_k: int = 10) -> list[IndexHit]:
        mode = mode.lower()
        if mode not in {"semantic", "keyword", "hybrid"}:
            raise ValueError("mode must be semantic, keyword, or hybrid")
        if top_k <= 0:
            return []
        candidate_limit = max(top_k * 5, 50)
        if mode == "semantic":
            ranked = self._semantic_hits(query, top_k)
        elif mode == "keyword":
            ranked = self._keyword_hits(query, top_k)
        else:
            semantic = self._semantic_hits(query, candidate_limit)
            keyword = self._keyword_hits(query, candidate_limit)
            fused: dict[int, float] = {}
            for candidates in (semantic, keyword):
                for rank, (row_id, _) in enumerate(candidates, start=1):
                    fused[row_id] = fused.get(row_id, 0.0) + 1.0 / (_RRF_K + rank)
            ranked = sorted(fused.items(), key=lambda item: item[1], reverse=True)[:top_k]
        if not ranked:
            return []
        row_ids = [row_id for row_id, _ in ranked]
        placeholders = ",".join("?" for _ in row_ids)
        rows = self.conn.execute(
            f"""
            SELECT c.row_id, c.chunk_id, f.relative_path
            FROM chunks c JOIN files f ON f.file_id = c.file_id
            WHERE c.row_id IN ({placeholders})
            """,
            row_ids,
        ).fetchall()
        references = {int(row["row_id"]): row for row in rows}
        return [
            IndexHit(
                relative_path=references[row_id]["relative_path"],
                chunk_id=references[row_id]["chunk_id"],
                score=score,
            )
            for row_id, score in ranked
            if row_id in references
        ]

