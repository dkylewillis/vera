"""Benchmark folder fan-out against the local VERA collection index."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
import tracemalloc
from pathlib import Path

from vera.collection import build_library_index
from vera.core.embeddings import HashingEmbedder, serialize_vector
from vera.core.schema import create_schema
from vera.corpus import VeraCorpus


def _write_vera(path: Path, document_number: int, chunks_per_document: int) -> None:
    embedder = HashingEmbedder()
    texts = [
        (
            f"Proposal {document_number} project experience section {chunk}. "
            f"Municipal infrastructure planning design construction administration topic{document_number}."
        )
        for chunk in range(chunks_per_document)
    ]
    vectors = embedder.embed(texts)
    conn = sqlite3.connect(path)
    try:
        create_schema(conn)
        metadata = {
            "format_name": "VERA",
            "format_version": "0.1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "created_by": "benchmark",
            "creator_library": "vera-benchmark",
            "source_file_name": f"proposal-{document_number}.pdf",
            "source_file_hash": f"{document_number:064x}",
            "source_mime_type": "application/pdf",
            "default_embedding_model": embedder.model_name,
            "default_embedding_dimension": str(embedder.dimension),
            "chunking_strategy": "benchmark",
            "parser_name": "benchmark",
            "parser_version": "1",
        }
        conn.executemany("INSERT INTO vera_metadata VALUES (?, ?)", metadata.items())
        doc_id = f"doc_{document_number:06d}"
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id,
                f"Proposal {document_number}",
                f"proposal-{document_number}.pdf",
                "application/pdf",
                metadata["source_file_hash"],
                1,
                metadata["created_at"],
            ),
        )
        conn.execute("INSERT INTO pages VALUES (?, ?, ?, ?, ?, ?)", (f"page_{document_number}", doc_id, 1, 612, 792, ""))
        for chunk, (text, vector) in enumerate(zip(texts, vectors)):
            chunk_id = f"chunk_{chunk:06d}"
            conn.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (chunk_id, doc_id, 1, 1, "Project Experience", text, len(text.split()), str(chunk), chunk),
            )
            conn.execute("INSERT INTO chunks_fts VALUES (?, ?, ?)", (chunk_id, text, "Project Experience"))
            conn.execute(
                "INSERT INTO embeddings VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"emb_{chunk:06d}", chunk_id, embedder.model_name, embedder.dimension, serialize_vector(vector), "float32_le", metadata["created_at"]),
            )
        conn.execute(
            "INSERT INTO assets VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("original", doc_id, "original_document", "application/pdf", f"proposal-{document_number}.pdf", b"benchmark", metadata["source_file_hash"]),
        )
        conn.commit()
    finally:
        conn.close()


def _time_search(
    root: Path,
    query: str,
    runs: int,
    *,
    use_index: bool,
) -> tuple[list[float], list[str | None]]:
    timings = []
    top_files = []
    with VeraCorpus.open(str(root), use_index=use_index) as corpus:
        for _ in range(runs):
            started = time.perf_counter()
            results = corpus.search(query, mode="hybrid", top_k=10)
            timings.append(time.perf_counter() - started)
            top_files.append(Path(results[0].file).name if results else None)
    return timings, top_files


def _peak_python_memory(root: Path, query: str, *, use_index: bool) -> int:
    tracemalloc.start()
    with VeraCorpus.open(str(root), use_index=use_index) as corpus:
        corpus.search(query, mode="hybrid", top_k=10)
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak_bytes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--documents", type=int, default=100)
    parser.add_argument("--chunks", type=int, default=100, help="Chunks per document")
    parser.add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    for name in ("documents", "chunks", "runs"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name} must be greater than zero")

    with tempfile.TemporaryDirectory(prefix="vera-benchmark-") as temporary:
        root = Path(temporary)
        for number in range(args.documents):
            _write_vera(root / f"proposal-{number:05d}.vera", number, args.chunks)
        query = f"municipal infrastructure topic{args.documents - 1}"
        expected_file = f"proposal-{args.documents - 1:05d}.vera"
        fanout, fanout_top_files = _time_search(
            root,
            query,
            args.runs,
            use_index=False,
        )
        fanout_peak_bytes = _peak_python_memory(root, query, use_index=False)
        build_started = time.perf_counter()
        report = build_library_index(str(root))
        build_seconds = time.perf_counter() - build_started
        indexed, indexed_top_files = _time_search(
            root,
            query,
            args.runs,
            use_index=True,
        )
        indexed_peak_bytes = _peak_python_memory(root, query, use_index=True)
        library_bytes = sum(path.stat().st_size for path in root.glob("*.vera"))
        index_bytes = sum(path.stat().st_size for path in (root / ".vera-index").rglob("*") if path.is_file())

    payload = {
        "documents": args.documents,
        "chunks_per_document": args.chunks,
        "total_chunks": args.documents * args.chunks,
        "runs": args.runs,
        "fanout_seconds": fanout,
        "indexed_seconds": indexed,
        "fanout_median_seconds": sorted(fanout)[len(fanout) // 2],
        "indexed_median_seconds": sorted(indexed)[len(indexed) // 2],
        "index_build_seconds": build_seconds,
        "indexed_files": report["indexed"],
        "expected_file": expected_file,
        "fanout_top_files": fanout_top_files,
        "indexed_top_files": indexed_top_files,
        "fanout_hit_rate": sum(path == expected_file for path in fanout_top_files) / args.runs,
        "indexed_hit_rate": sum(path == expected_file for path in indexed_top_files) / args.runs,
        "fanout_python_peak_bytes": fanout_peak_bytes,
        "indexed_python_peak_bytes": indexed_peak_bytes,
        "library_bytes": library_bytes,
        "index_bytes": index_bytes,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
