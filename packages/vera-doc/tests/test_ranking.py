"""Unit tests for hybrid ranking helpers."""

import pytest

from vera_doc.ranking import combine_hybrid_scores, normalize_scores, reciprocal_rank_fusion


class TestRanking:
    def test_normalize_scores_unit_interval(self):
        assert normalize_scores({"a": 2.0, "b": 4.0, "c": 6.0}) == {
            "a": 0.0,
            "b": 0.5,
            "c": 1.0,
        }

    def test_combine_hybrid_scores_respects_weights(self):
        semantic = {"a": 1.0, "b": 0.0}
        keyword = {"a": 0.0, "b": 1.0}
        balanced = combine_hybrid_scores(semantic, keyword)
        assert balanced["a"] == pytest.approx(0.5)
        assert balanced["b"] == pytest.approx(0.5)
        semantic_heavy = combine_hybrid_scores(
            semantic, keyword, semantic_weight=1.0, keyword_weight=0.0
        )
        assert semantic_heavy["a"] == pytest.approx(1.0)
        assert semantic_heavy["b"] == pytest.approx(0.0)

    def test_reciprocal_rank_fusion_prefers_shared_ranks(self):
        fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]])
        assert [item for item, _ in fused][0] == "b"

    def test_normalize_scores_empty_and_constant(self):
        assert normalize_scores({}) == {}
        assert normalize_scores({"a": 3.0, "b": 3.0}) == {"a": 1.0, "b": 1.0}

    def test_combine_hybrid_scores_includes_disjoint_ids(self):
        combined = combine_hybrid_scores({"a": 1.0}, {"b": 1.0})
        assert set(combined) == {"a", "b"}
        assert combined["a"] == pytest.approx(0.5)
        assert combined["b"] == pytest.approx(0.5)

    def test_combine_hybrid_scores_rejects_non_positive_weights(self):
        with pytest.raises(ValueError, match="positive"):
            combine_hybrid_scores({"a": 1.0}, {"a": 1.0}, semantic_weight=0.0, keyword_weight=0.0)

    def test_reciprocal_rank_fusion_empty_and_stable_tie_break(self):
        assert reciprocal_rank_fusion([]) == []
        fused = reciprocal_rank_fusion([["b", "a"], ["a", "b"]])
        assert [item for item, _ in fused] == ["a", "b"]
