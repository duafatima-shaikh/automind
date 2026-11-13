"""Turn text into vectors.

Two backends:
  * sentence-transformers: real meaning based embeddings (recommended).
  * hash: an offline word hashing encoder. It needs no download and is fully deterministic,
    which makes tests fast. It matches words, not meaning, so quality is lower.
"""
from __future__ import annotations

import logging
import zlib
from typing import Protocol, Sequence

import numpy as np

from ..config import Settings
from ..utils.text import tokenize

logger = logging.getLogger(__name__)


class Encoder(Protocol):
    name: str
    dim: int

    def encode(self, texts: Sequence[str]) -> np.ndarray: ...


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class HashingEncoder:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        matrix = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = tokenize(text)
            features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
            for feature in features:
                code = zlib.crc32(feature.encode("utf-8"))
                sign = 1.0 if (code >> 31) & 1 else -1.0
                matrix[row, code % self.dim] += sign
            # dampen repeated words
            matrix[row] = np.sign(matrix[row]) * np.log1p(np.abs(matrix[row]))
        return _normalize(matrix)


class SentenceTransformerEncoder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.name = model_name

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vectors = self.model.encode(
            list(texts), batch_size=32, normalize_embeddings=True, show_progress_bar=False
        )
        return np.asarray(vectors, dtype=np.float32)


def build_encoder(settings: Settings) -> Encoder:
    backend = settings.embedding_backend
    if backend == "hash":
        return HashingEncoder(settings.hash_embedding_dim)
    try:
        return SentenceTransformerEncoder(settings.embedding_model)
    except Exception as error:  # noqa: BLE001
        if backend == "sentence-transformers":
            raise
        logger.warning(
            "Could not load sentence-transformers (%s). Falling back to the hash encoder. "
            "Answers will be less accurate. Install with: pip install 'automind[ml]'",
            error,
        )
        return HashingEncoder(settings.hash_embedding_dim)
