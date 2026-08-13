"""Score normalization, hybrid weighting, and reciprocal-rank fusion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

RRF_K = 60.0
DEFAULT_HYBRID_SEMANTIC_WEIGHT = 0.5
DEFAULT_HYBRID_KEYWORD_WEIGHT = 0.5

T = TypeVar("T")


def normalize_scores(scores: Mapping[str, float]) -> dict[str, float]:
    """Min-max normalize a score mapping to the unit interval."""
    if not scores:
        return {}
    values = list(scores.values())
    low, high = min(values), max(values)
    if high == low:
        return {key: 1.0 for key in scores}
    return {key: (value - low) / (high - low) for key, value in scores.items()}


def combine_hybrid_scores(
    semantic: Mapping[str, float],
    keyword: Mapping[str, float],
    *,
    semantic_weight: float = DEFAULT_HYBRID_SEMANTIC_WEIGHT,
    keyword_weight: float = DEFAULT_HYBRID_KEYWORD_WEIGHT,
) -> dict[str, float]:
    """Blend min-max-normalized semantic and keyword scores."""
    total = semantic_weight + keyword_weight
    if total <= 0:
        raise ValueError("hybrid weights must sum to a positive value")
    semantic_norm = normalize_scores(semantic)
    keyword_norm = normalize_scores(keyword)
    semantic_share = semantic_weight / total
    keyword_share = keyword_weight / total
    return {
        record_id: semantic_share * semantic_norm.get(record_id, 0.0)
        + keyword_share * keyword_norm.get(record_id, 0.0)
        for record_id in semantic.keys() | keyword.keys()
    }


def reciprocal_rank_fusion(
    ranked_lists: Sequence[Sequence[T]],
    *,
    k: float = RRF_K,
) -> list[tuple[T, float]]:
    """Fuse ranked lists with reciprocal rank fusion and a stable id tie-break."""
    fused: dict[T, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(fused.items(), key=lambda item: (-item[1], item[0]))
