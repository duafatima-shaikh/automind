"""Maximal marginal relevance: pick results that are relevant but not repeats of each other."""
from __future__ import annotations

import numpy as np


def mmr_select(
    vectors: np.ndarray, relevance: list[float], k: int, lambda_: float = 0.7
) -> list[int]:
    """Return the positions of the chosen items, in the order they were picked."""
    count = len(relevance)
    if count == 0:
        return []
    k = min(k, count)
    similarity = vectors @ vectors.T
    selected: list[int] = []
    remaining = list(range(count))
    while remaining and len(selected) < k:
        best, best_score = remaining[0], -np.inf
        for candidate in remaining:
            redundancy = max((similarity[candidate, s] for s in selected), default=0.0)
            score = lambda_ * relevance[candidate] - (1 - lambda_) * redundancy
            if score > best_score:
                best, best_score = candidate, score
        selected.append(best)
        remaining.remove(best)
    return selected
