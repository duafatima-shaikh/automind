"""Scoring functions for retrieval and answers."""
from __future__ import annotations

from typing import Optional, Sequence

from ..utils.metrics import percentile


def first_hit_rank(chunk_texts: Sequence[str], evidence: str) -> Optional[int]:
    """1 based rank of the first retrieved chunk containing the evidence text, or None."""
    needle = " ".join(evidence.lower().split())
    for rank, text in enumerate(chunk_texts, start=1):
        if needle in " ".join(text.lower().split()):
            return rank
    return None


def hit_at_k(ranks: Sequence[Optional[int]], k: int) -> float:
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else 0.0


def mean_reciprocal_rank(ranks: Sequence[Optional[int]]) -> float:
    return sum(1.0 / r for r in ranks if r) / len(ranks) if ranks else 0.0


def keywords_present(answer: str, keywords: Sequence[str]) -> bool:
    lowered = answer.lower()
    return all(k.lower() in lowered for k in keywords)


def latency_summary(seconds: Sequence[float]) -> dict:
    values = [s * 1000 for s in seconds]
    return {
        "mean_ms": round(sum(values) / len(values), 2) if values else 0.0,
        "p95_ms": round(percentile(values, 95), 2),
    }
