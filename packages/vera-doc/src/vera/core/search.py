from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from .embeddings import cosine_similarity, deserialize_vector, get_embedder


@dataclass
class SearchResult:
    chunk_id: str
    score: float
    text: str
    page_start: int | None
    page_end: int | None
    heading_path: str | None
    source_filename: str | None
    document_id: str
    before_chunks: list[dict[str, Any]] | None = None
    after_chunks: list[dict[str, Any]] | None = None

    def as_dict(self) -> dict[str, Any]:
        data = self.__dict__.copy()
        if self.before_chunks is None:
            data.pop("before_chunks")
        if self.after_chunks is None:
            data.pop("after_chunks")
        return data


def search_document(
    conn: sqlite3.Connection,
    query: str,
    mode: str = "hybrid",
    top_k: int = 10,
    context_chunks: int = 0,
) -> list[SearchResult]:
    mode = mode.lower()
    if mode not in {"semantic", "keyword", "hybrid"}:
        raise ValueError("mode must be semantic, keyword, or hybrid")
    if context_chunks < 0:
        raise ValueError("context_chunks must be non-negative")
    if mode == "semantic":
        results = semantic_search(conn, query, top_k)
    elif mode == "keyword":
        results = keyword_search(conn, query, top_k)
    else:
        results = hybrid_search(conn, query, top_k)
    if context_chunks:
        add_context_chunks(conn, results, context_chunks)
    return results


def add_context_chunks(conn: sqlite3.Connection, results: list[SearchResult], context_chunks: int) -> None:
    for result in results:
        before_chunks, after_chunks = context_chunks_for(conn, result.chunk_id, context_chunks)
        result.before_chunks = before_chunks
        result.after_chunks = after_chunks


def context_chunks_for(
    conn: sqlite3.Connection,
    chunk_id: str,
    context_chunks: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    origin = conn.execute(
        "SELECT document_id, sort_order FROM chunks WHERE chunk_id = ?",
        (chunk_id,),
    ).fetchone()
    if origin is None:
        return [], []

    before_rows = conn.execute(
        """
        SELECT c.*, d.source_filename
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.document_id = ? AND c.sort_order < ?
        ORDER BY c.sort_order DESC
        LIMIT ?
        """,
        (origin["document_id"], origin["sort_order"], context_chunks),
    ).fetchall()
    after_rows = conn.execute(
        """
        SELECT c.*, d.source_filename
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.document_id = ? AND c.sort_order > ?
        ORDER BY c.sort_order ASC
        LIMIT ?
        """,
        (origin["document_id"], origin["sort_order"], context_chunks),
    ).fetchall()
    return (
        [row_to_context_chunk(row) for row in reversed(before_rows)],
        [row_to_context_chunk(row) for row in after_rows],
    )


def row_to_context_chunk(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "chunk_id": row["chunk_id"],
        "text": row["text"],
        "page_start": row["page_start"],
        "page_end": row["page_end"],
        "heading_path": row["heading_path"],
        "source_filename": row["source_filename"],
        "document_id": row["document_id"],
    }


def row_to_result(row: sqlite3.Row, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=row["chunk_id"],
        score=float(score),
        text=row["text"],
        page_start=row["page_start"],
        page_end=row["page_end"],
        heading_path=row["heading_path"],
        source_filename=row["source_filename"],
        document_id=row["document_id"],
    )


def semantic_scores(conn: sqlite3.Connection, query: str) -> list[SearchResult]:
    """Score every chunk against the query (brute-force cosine), unsorted."""
    metadata = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM vera_metadata")}
    embedder = get_embedder(metadata.get("default_embedding_model") or "hashing")
    query_vec = embedder.embed([query])[0]
    rows = conn.execute(
        """
        SELECT c.*, d.source_filename, e.vector
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        JOIN embeddings e ON e.chunk_id = c.chunk_id
        ORDER BY c.sort_order
        """
    ).fetchall()
    scored = []
    for row in rows:
        vec = deserialize_vector(row["vector"])
        scored.append(row_to_result(row, cosine_similarity(query_vec, vec)))
    return scored


def semantic_search(conn: sqlite3.Connection, query: str, top_k: int) -> list[SearchResult]:
    scored = semantic_scores(conn, query)
    return sorted(scored, key=lambda r: r.score, reverse=True)[:top_k]


def keyword_search(conn: sqlite3.Connection, query: str, top_k: int) -> list[SearchResult]:
    # FTS5 bm25 is lower-is-better; convert to bounded positive-ish score.
    sql = """
        SELECT c.*, d.source_filename, bm25(chunks_fts) AS rank
        FROM chunks_fts
        JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
        JOIN documents d ON c.document_id = d.document_id
        WHERE chunks_fts MATCH ?
        ORDER BY rank LIMIT ?
    """

    def safe_query(raw: str) -> str:
        terms = []
        for token in raw.split():
            cleaned = "".join(ch for ch in token if ch.isalnum() or ch == "_")
            if cleaned:
                terms.append(f"{cleaned}*")
        return " OR ".join(terms) or raw

    try:
        rows = conn.execute(sql, (query, top_k)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:
        rows = conn.execute(sql, (safe_query(query), top_k)).fetchall()
    results = []
    for row in rows:
        rank = float(row["rank"])
        score = 1.0 / (1.0 + max(rank, 0.0)) if rank >= 0 else 1.0 + abs(rank)
        results.append(row_to_result(row, score))
    return results


def hybrid_search(conn: sqlite3.Connection, query: str, top_k: int) -> list[SearchResult]:
    """Fuse semantic and keyword scores: hybrid = semantic*0.5 + keyword*0.5."""
    semantic = semantic_scores(conn, query)
    keyword = keyword_search(conn, query, max(top_k * 5, 50))

    def normalize(results: list[SearchResult]) -> dict[str, float]:
        if not results:
            return {}
        scores = [r.score for r in results]
        lo, hi = min(scores), max(scores)
        if hi <= lo:
            return {r.chunk_id: 1.0 for r in results}
        return {r.chunk_id: (r.score - lo) / (hi - lo) for r in results}

    sem_norm = normalize(semantic)
    key_norm = normalize(keyword)
    by_id = {r.chunk_id: r for r in semantic}
    for result in keyword:
        by_id.setdefault(result.chunk_id, result)
    results = []
    for chunk_id, result in by_id.items():
        combined = sem_norm.get(chunk_id, 0.0) * 0.5 + key_norm.get(chunk_id, 0.0) * 0.5
        copy = SearchResult(**result.as_dict())
        copy.score = combined
        results.append(copy)
    return sorted(results, key=lambda r: r.score, reverse=True)[:top_k]
