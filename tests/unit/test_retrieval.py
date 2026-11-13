import numpy as np

from automind.retrieval.mmr import mmr_select
from automind.retrieval.reranker import LexicalReranker
from automind.retrieval.retriever import reciprocal_rank_fusion


def test_rrf_prefers_items_found_by_both_lists():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["b", "d"]])
    assert max(fused, key=fused.get) == "b"


def test_mmr_avoids_duplicates():
    vectors = np.array([[1, 0], [1, 0], [0, 1]], dtype=np.float32)
    picks = mmr_select(vectors, [1.0, 0.95, 0.6], k=2, lambda_=0.5)
    assert picks == [0, 2]


def test_lexical_reranker_scores_matching_text_higher():
    scores = LexicalReranker().score(
        "monthly pass price", ["The monthly pass price is 18 dollars", "Coffee is brewed hot"]
    )
    assert scores[0] > scores[1]
    assert all(0 <= s <= 1 for s in scores)
