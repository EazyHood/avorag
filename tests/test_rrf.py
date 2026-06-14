"""Tests de Reciprocal Rank Fusion (puro)."""

from avorag.retrieval.hybrid import reciprocal_rank_fusion


def test_rrf_doc_high_in_both_lists_wins():
    dense = ["a", "b", "c"]
    lexical = ["a", "c", "b"]
    fused = reciprocal_rank_fusion([dense, lexical], k=60)
    assert fused[0][0] == "a"  # primero en ambas


def test_rrf_merges_disjoint_lists():
    fused = reciprocal_rank_fusion([["a", "b"], ["c", "d"]], k=60)
    ids = {doc for doc, _ in fused}
    assert ids == {"a", "b", "c", "d"}


def test_rrf_scores_descending():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "b", "c"]], k=60)
    scores = [s for _, s in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_empty():
    assert reciprocal_rank_fusion([], k=60) == []
