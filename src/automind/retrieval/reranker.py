"""Second pass scoring of the best candidates. Scores are always between 0 and 1."""
from __future__ import annotations

import logging
import math
from typing import Optional, Protocol, Sequence

from ..config import Settings
from ..utils.text import content_terms

logger = logging.getLogger(__name__)


class Reranker(Protocol):
    def score(self, query: str, texts: Sequence[str]) -> list[float]: ...


class LexicalReranker:
    """Rewards chunks that contain the question's words and its word pairs in order."""

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        terms = content_terms(query)
        unique = set(terms)
        pairs = set(zip(terms, terms[1:]))
        scores = []
        for text in texts:
            chunk_terms = content_terms(text)
            if not unique:
                scores.append(0.0)
                continue
            coverage = len(unique & set(chunk_terms)) / len(unique)
            chunk_pairs = set(zip(chunk_terms, chunk_terms[1:]))
            pair_score = len(pairs & chunk_pairs) / len(pairs) if pairs else 0.0
            scores.append(0.7 * coverage + 0.3 * pair_score)
        return scores


class CrossEncoderReranker:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import CrossEncoder

        self.model = CrossEncoder(model_name)

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        raw = self.model.predict([(query, t) for t in texts], show_progress_bar=False)
        return [1.0 / (1.0 + math.exp(-float(x))) for x in raw]


def build_reranker(settings: Settings) -> Optional[Reranker]:
    if settings.reranker == "none":
        return None
    if settings.reranker == "cross-encoder":
        try:
            return CrossEncoderReranker(settings.cross_encoder_model)
        except Exception as error:  # noqa: BLE001
            logger.warning("Cross encoder unavailable (%s). Using the lexical reranker.", error)
    return LexicalReranker()
