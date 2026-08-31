"""Semantic, keyword, and hybrid search for VeraDocument."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

import numpy as np

from ._fts import execute_fts, safe_fts_query
from ._util import _MAX_TOP_K, SearchMode
from ._where import metadata_matches
from .embeddings import EmbeddingFunction, deserialize_vector, get_embedder
from .models import ChunkRecord, QueryResult, metadata_from_json, thaw_json
from .ranking import (
    DEFAULT_HYBRID_KEYWORD_WEIGHT,
    DEFAULT_HYBRID_SEMANTIC_WEIGHT,
    combine_hybrid_scores,
)


class _DocumentSearchMixin:
    _conn: sqlite3.Connection
    _embedding_function: EmbeddingFunction | None

    if TYPE_CHECKING:

        def _ensure_open(self) -> None: ...
        def _metadata_values(self) -> dict[str, str]: ...
        def get(
            self,
            ids: Iterable[str] | None = None,
            *,
            where: Mapping[str, Any] | None = None,
            limit: int | None = None,
        ) -> list[ChunkRecord]: ...

    def search(
        self,
        text: str | None = None,
        *,
        vector: Sequence[float] | None = None,
        mode: SearchMode = "hybrid",
        where: Mapping[str, Any] | None = None,
        top_k: int = 10,
        context_chunks: int = 0,
        semantic_weight: float = DEFAULT_HYBRID_SEMANTIC_WEIGHT,
        keyword_weight: float = DEFAULT_HYBRID_KEYWORD_WEIGHT,
    ) -> list[QueryResult]:
        """Search chunk records.

        Args:
            text: Query string for semantic or keyword search. Required unless
                ``vector`` is supplied for semantic mode.
            vector: Pre-computed query vector for semantic search.
            mode: ``"hybrid"`` (default), ``"semantic"``, or ``"keyword"``.
            where: Filter on top-level metadata keys, applied before
                ``top_k``. Scalars are exact equality; a list, tuple, or set
                value is IN. Distinct keys are AND.
            top_k: Maximum number of results to return.
            context_chunks: Number of adjacent stored chunks to include.
            semantic_weight: Hybrid blend weight for semantic scores.
            keyword_weight: Hybrid blend weight for keyword scores.

        Returns:
            Ranked :class:`~vera_doc.models.QueryResult` objects.
        """
        self._ensure_open()
        if mode not in {"semantic", "keyword", "hybrid"}:
            raise ValueError("mode must be semantic, keyword, or hybrid")
        if top_k < 0:
            raise ValueError("top_k must be non-negative")
        if top_k > _MAX_TOP_K:
            raise ValueError(f"top_k must be at most {_MAX_TOP_K}")
        if context_chunks < 0:
            raise ValueError("context_chunks must be non-negative")
        if top_k == 0:
            return []
        if mode in {"keyword", "hybrid"} and not text:
            raise ValueError(f"{mode} search requires text")
        semantic: dict[str, float] = {}
        keyword: dict[str, float] = {}
        if mode in {"semantic", "hybrid"}:
            query_vector = self._query_vector(text=text, vector=vector)
            semantic = self._semantic_scores(query_vector)
        if mode in {"keyword", "hybrid"}:
            keyword = self._keyword_scores(text or "")
        if mode == "semantic":
            combined = semantic
        elif mode == "keyword":
            combined = keyword
        else:
            combined = combine_hybrid_scores(
                semantic,
                keyword,
                semantic_weight=semantic_weight,
                keyword_weight=keyword_weight,
            )
        matching_ids = self._chunk_ids(where)
        ranked = sorted(
            (
                (record_id, score)
                for record_id, score in combined.items()
                if record_id in matching_ids
            ),
            key=lambda item: (-item[1], item[0]),
        )[:top_k]
        needed = [record_id for record_id, _ in ranked]
        ordered_ids: list[str] = []
        if context_chunks and needed:
            ordered_ids = self._chunk_ids_in_order()
            positions = {chunk_id: index for index, chunk_id in enumerate(ordered_ids)}
            extra: list[str] = []
            for record_id in needed:
                position = positions.get(record_id)
                if position is None:
                    continue
                extra.extend(ordered_ids[max(0, position - context_chunks) : position])
                extra.extend(ordered_ids[position + 1 : position + context_chunks + 1])
            needed = list(dict.fromkeys([*needed, *extra]))
        records = {record.id: record for record in self.get(needed)}
        results = [
            QueryResult(
                record=records[record_id],
                score=float(score),
                semantic_score=semantic.get(record_id),
                keyword_score=keyword.get(record_id),
            )
            for record_id, score in ranked
            if record_id in records
        ]
        if context_chunks and ordered_ids:
            by_id = records
            positions = {chunk_id: index for index, chunk_id in enumerate(ordered_ids)}
            results = [
                replace(
                    result,
                    before=tuple(
                        by_id[chunk_id]
                        for chunk_id in ordered_ids[
                            max(0, positions[result.record.id] - context_chunks) : positions[
                                result.record.id
                            ]
                        ]
                        if chunk_id in by_id
                    ),
                    after=tuple(
                        by_id[chunk_id]
                        for chunk_id in ordered_ids[
                            positions[result.record.id] + 1 : positions[result.record.id]
                            + context_chunks
                            + 1
                        ]
                        if chunk_id in by_id
                    ),
                )
                for result in results
            ]
        return results

    def _query_vector(
        self,
        *,
        text: str | None,
        vector: Sequence[float] | None,
    ) -> np.ndarray:
        expected = int(self._metadata_values()["default_embedding_dimension"])
        if vector is None:
            if text is None:
                raise ValueError("semantic search requires text or vector")
            embedder = self._embedding_function
            if embedder is None:
                model_name = self._metadata_values()["default_embedding_model"]
                embedder = get_embedder(model_name)
            query = np.asarray(embedder.embed([text])[0], dtype=np.float32)
        else:
            query = np.asarray(vector, dtype=np.float32)
        if query.ndim != 1 or query.size != expected:
            raise ValueError(
                f"query vector dimension {query.size} does not match database dimension {expected}"
            )
        if not np.isfinite(query).all():
            raise ValueError("query vector must contain only finite numbers")
        return query

    def _semantic_scores(self, query: np.ndarray) -> dict[str, float]:
        query_norm = float(np.linalg.norm(query))
        if query_norm == 0:
            return {}
        rows = self._conn.execute("SELECT chunk_id, vector FROM embeddings").fetchall()
        if not rows:
            return {}
        ids = [str(row["chunk_id"]) for row in rows]
        matrix = np.vstack([deserialize_vector(row["vector"]) for row in rows])
        doc_norms = np.linalg.norm(matrix, axis=1)
        dots = matrix @ query
        scores = np.divide(
            dots,
            doc_norms * query_norm,
            out=np.zeros(dots.shape, dtype=np.float64),
            where=doc_norms != 0,
        )
        return {chunk_id: float(score) for chunk_id, score in zip(ids, scores, strict=True)}

    def _keyword_scores(self, text: str) -> dict[str, float]:
        sql = """
            SELECT chunk_id, bm25(chunks_fts) AS rank
            FROM chunks_fts
            WHERE chunks_fts MATCH ?
        """
        rows = execute_fts(self._conn, sql, text)
        if not rows:
            fallback = safe_fts_query(text)
            if fallback:
                rows = execute_fts(self._conn, sql, fallback)
        return {row["chunk_id"]: -float(row["rank"]) for row in rows}

    def _chunk_ids(self, where: Mapping[str, Any] | None) -> set[str]:
        if not where:
            return {str(row[0]) for row in self._conn.execute("SELECT chunk_id FROM chunks")}
        matching: set[str] = set()
        for row in self._conn.execute("SELECT chunk_id, metadata_json FROM chunks"):
            metadata = thaw_json(metadata_from_json(row["metadata_json"]))
            if metadata_matches(metadata, where):
                matching.add(str(row["chunk_id"]))
        return matching

    def _chunk_ids_in_order(self) -> list[str]:
        return [
            str(row[0]) for row in self._conn.execute("SELECT chunk_id FROM chunks ORDER BY rowid")
        ]
