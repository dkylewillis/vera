"""Rebuildable library-level search index for collections of .vera files."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from ._fts import execute_fts, safe_fts_query
from ._index_build import (
    build_library_index,
    library_index_status,
    update_library_index,
)
from ._index_layout import (
    INDEX_DATABASE,
    INDEX_DIRECTORY,
    INDEX_GENERATIONS,
    INDEX_LOCK,
    INDEX_POINTER,
    INDEX_VERSION,
    _generation_path,
    discover_vera_files,
)
from ._util import _MAX_TOP_K
from .embeddings import get_embedder
from .ranking import reciprocal_rank_fusion

__all__ = [
    "INDEX_DATABASE",
    "INDEX_DIRECTORY",
    "INDEX_GENERATIONS",
    "INDEX_LOCK",
    "INDEX_POINTER",
    "INDEX_VERSION",
    "IndexHit",
    "VeraCollectionIndex",
    "build_library_index",
    "discover_vera_files",
    "library_index_status",
    "update_library_index",
]


@dataclass(frozen=True)
class IndexHit:
    """A ranked index hit that can be resolved against its source .vera file."""

    relative_path: str
    chunk_id: str
    score: float


class VeraCollectionIndex:
    """Opened local collection index used by VeraCorpus when it is fresh."""

    def __init__(self, root: Path, generation: Path, conn: sqlite3.Connection):
        self.root = root
        self.generation = generation
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._matrices: dict[str, np.ndarray] = {}
        self.skipped_semantic_model_groups: list[dict[str, Any]] = []

    @classmethod
    def open(cls, directory: str, *, check_status: bool = True) -> VeraCollectionIndex:
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

    def document_paths(self, *, include_skipped: bool = True) -> list[str]:
        """Return root-relative archive paths recorded by this generation."""
        paths = [
            str(row["relative_path"])
            for row in self.conn.execute("SELECT relative_path FROM files")
        ]
        if include_skipped:
            paths.extend(
                str(row["relative_path"])
                for row in self.conn.execute("SELECT relative_path FROM skipped_files")
            )
        return sorted(paths, key=str.lower)

    def inspect_summary(self) -> dict[str, Any]:
        """Return corpus metrics from the persistent index without reopening archives."""
        files = []
        total_pages = 0
        total_chunks = 0
        models: set[str] = set()
        rows = self.conn.execute(
            """
            SELECT
                f.relative_path,
                f.source_filename,
                f.metadata_json,
                COUNT(c.row_id) AS chunk_count,
                MAX(COALESCE(c.page_end, c.page_start, 0)) AS highest_chunk_page
            FROM files f
            LEFT JOIN chunks c ON c.file_id = f.file_id
            GROUP BY f.file_id
            ORDER BY f.relative_path
            """
        )
        for row in rows:
            try:
                metadata = json.loads(row["metadata_json"])
            except (TypeError, json.JSONDecodeError):
                metadata = {}
            pages = int(metadata.get("_vera_page_count") or row["highest_chunk_page"] or 0)
            chunks = int(row["chunk_count"] or 0)
            model = str(metadata.get("default_embedding_model") or "")
            path = str((self.root / row["relative_path"]).resolve())
            files.append(
                {
                    "file": path,
                    "source": row["source_filename"],
                    "pages": pages,
                    "chunks": chunks,
                    "embedding_model": model or None,
                }
            )
            total_pages += pages
            total_chunks += chunks
            if model:
                models.add(model)
        return {
            "file_count": len(files),
            "pages": total_pages,
            "chunks": total_chunks,
            "embedding_models": sorted(models),
            "files": files,
        }

    def __enter__(self) -> VeraCollectionIndex:
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
        for group in self.conn.execute(
            "SELECT * FROM vector_groups ORDER BY model_name, dimension"
        ):
            try:
                embedder = get_embedder(group["model_name"])
                if embedder.dimension != group["dimension"]:
                    self.skipped_semantic_model_groups.append(
                        {
                            "model_name": str(group["model_name"]),
                            "dimension": int(group["dimension"]),
                            "error": (
                                f"Runtime model dimension {embedder.dimension} does not match "
                                f"indexed dimension {group['dimension']}"
                            ),
                        }
                    )
                    continue
                query_vector = np.asarray(embedder.embed([query])[0], dtype=np.float32)
            except Exception as exc:
                # Keyword search remains available when a recorded model cannot
                # be loaded in the current environment.
                self.skipped_semantic_model_groups.append(
                    {
                        "model_name": str(group["model_name"]),
                        "dimension": int(group["dimension"]),
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
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
                [
                    (row_ids[position], float(scores[position]))
                    for position in vector_rows
                    if position in row_ids
                ]
            )
        if not per_group:
            return []
        if len(per_group) == 1:
            return per_group[0][:limit]
        fused = reciprocal_rank_fusion(
            [[row_id for row_id, _ in group_hits] for group_hits in per_group]
        )
        return fused[:limit]

    def _keyword_hits(self, query: str, limit: int) -> list[tuple[int, float]]:
        sql = """
            SELECT row_id, bm25(chunks_fts) AS rank
            FROM chunks_fts WHERE chunks_fts MATCH ?
            ORDER BY rank LIMIT ?
        """
        rows = execute_fts(self.conn, sql, query, limit)
        if not rows:
            fallback = safe_fts_query(query)
            if not fallback:
                return []
            rows = execute_fts(self.conn, sql, fallback, limit)
        hits = []
        for row in rows:
            rank = float(row["rank"])
            score = 1.0 / (1.0 + max(rank, 0.0)) if rank >= 0 else 1.0 + abs(rank)
            hits.append((int(row["row_id"]), score))
        return hits

    def _rows_by_id(self, row_ids: list[int]) -> dict[int, sqlite3.Row]:
        unique = list(dict.fromkeys(row_ids))
        if not unique:
            return {}
        placeholders = ",".join("?" for _ in unique)
        rows = self.conn.execute(
            f"""
            SELECT c.row_id, c.chunk_id, f.relative_path
            FROM chunks c JOIN files f ON f.file_id = c.file_id
            WHERE c.row_id IN ({placeholders})
            """,
            unique,
        ).fetchall()
        return {int(row["row_id"]): row for row in rows}

    def search(self, query: str, mode: str = "hybrid", top_k: int = 10) -> list[IndexHit]:
        mode = mode.lower()
        if mode not in {"semantic", "keyword", "hybrid"}:
            raise ValueError("mode must be semantic, keyword, or hybrid")
        self.skipped_semantic_model_groups = []
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if top_k > _MAX_TOP_K:
            raise ValueError(f"top_k must be at most {_MAX_TOP_K}")
        if top_k == 0:
            return []
        candidate_limit = max(top_k * 5, 50)
        if mode == "hybrid":
            semantic = self._semantic_hits(query, candidate_limit)
            keyword = self._keyword_hits(query, candidate_limit)
            references = self._rows_by_id(
                [row_id for row_id, _ in semantic] + [row_id for row_id, _ in keyword]
            )

            def hit_keys(hits: list[tuple[int, float]]) -> list[tuple[str, str]]:
                return [
                    (
                        str(references[row_id]["relative_path"]),
                        str(references[row_id]["chunk_id"]),
                    )
                    for row_id, _ in hits
                    if row_id in references
                ]

            return [
                IndexHit(relative_path=key[0], chunk_id=key[1], score=score)
                for key, score in reciprocal_rank_fusion([hit_keys(semantic), hit_keys(keyword)])[
                    :top_k
                ]
            ]
        if mode == "semantic":
            ranked = self._semantic_hits(query, top_k)
        else:
            ranked = self._keyword_hits(query, top_k)
        if not ranked:
            return []
        references = self._rows_by_id([row_id for row_id, _ in ranked])
        return [
            IndexHit(
                relative_path=references[row_id]["relative_path"],
                chunk_id=references[row_id]["chunk_id"],
                score=score,
            )
            for row_id, score in ranked
            if row_id in references
        ]
