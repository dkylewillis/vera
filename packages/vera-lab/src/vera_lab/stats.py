"""Aggregate statistics for a lab document."""

from __future__ import annotations

from collections import Counter
from typing import Any

from vera_lab.model import LabDocument


def compute_stats(document: LabDocument) -> dict[str, Any]:
    """Return corpus-level aggregates for the report."""
    blocks_by_type = Counter(block.block_type for block in document.blocks)
    chunks_per_page: Counter[int] = Counter()
    for chunk in document.chunks:
        for page in range(chunk.page_start, chunk.page_end + 1):
            chunks_per_page[page] += 1

    token_counts = [chunk.token_count for chunk in document.chunks]
    single_block = sum(1 for chunk in document.chunks if len(chunk.block_ids) == 1)
    multi_block = sum(1 for chunk in document.chunks if len(chunk.block_ids) > 1)
    zero_block = sum(1 for chunk in document.chunks if not chunk.block_ids)

    histogram = _token_histogram(token_counts)

    return {
        "page_count": len(document.pages),
        "block_count": len(document.blocks),
        "chunk_count": len(document.chunks),
        "figure_count": len(document.figures),
        "blocks_by_type": dict(sorted(blocks_by_type.items())),
        "chunks_per_page": {str(page): count for page, count in sorted(chunks_per_page.items())},
        "token_count": {
            "min": min(token_counts) if token_counts else 0,
            "max": max(token_counts) if token_counts else 0,
            "median": _median(token_counts),
            "mean": (sum(token_counts) / len(token_counts)) if token_counts else 0.0,
            "total": sum(token_counts),
            "histogram": histogram,
        },
        "chunk_block_linkage": {
            "single_block": single_block,
            "multi_block": multi_block,
            "zero_block": zero_block,
        },
        "parser_name": document.parser_name,
        "parser_version": document.parser_version,
        "chunking_strategy": document.chunking_strategy,
        "pipeline_spec": document.pipeline_spec,
        "mode": document.mode,
    }


def _median(values: list[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _token_histogram(token_counts: list[int], *, bucket_size: int = 50) -> list[dict[str, Any]]:
    if not token_counts:
        return []
    buckets: Counter[int] = Counter()
    for count in token_counts:
        buckets[(count // bucket_size) * bucket_size] += 1
    return [
        {
            "start": start,
            "end": start + bucket_size - 1,
            "count": buckets[start],
        }
        for start in sorted(buckets)
    ]
