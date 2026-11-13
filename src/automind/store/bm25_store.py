"""Keyword search with the BM25 formula. Good at exact words, names and numbers."""
from __future__ import annotations

import math
import threading
from collections import Counter
from typing import Iterable, Optional

from ..utils.text import tokenize


class BM25Store:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self._lock = threading.RLock()
        self._postings: dict[str, dict[str, int]] = {}
        self._terms: dict[str, Counter] = {}
        self._doc_of: dict[str, str] = {}
        self._lengths: dict[str, int] = {}
        self._total_length = 0

    def __len__(self) -> int:
        return len(self._lengths)

    def add(self, chunk_id: str, doc_id: str, text: str) -> None:
        tokens = tokenize(text)
        counts = Counter(tokens)
        with self._lock:
            if chunk_id in self._lengths:
                self._remove_chunk(chunk_id)
            self._terms[chunk_id] = counts
            self._doc_of[chunk_id] = doc_id
            self._lengths[chunk_id] = len(tokens)
            self._total_length += len(tokens)
            for term, count in counts.items():
                self._postings.setdefault(term, {})[chunk_id] = count

    def _remove_chunk(self, chunk_id: str) -> None:
        for term in self._terms.pop(chunk_id, {}):
            postings = self._postings.get(term)
            if postings:
                postings.pop(chunk_id, None)
                if not postings:
                    del self._postings[term]
        self._total_length -= self._lengths.pop(chunk_id, 0)
        self._doc_of.pop(chunk_id, None)

    def remove_document(self, doc_id: str) -> None:
        with self._lock:
            for chunk_id in [c for c, d in self._doc_of.items() if d == doc_id]:
                self._remove_chunk(chunk_id)

    def rebuild(self, chunks: Iterable) -> None:
        with self._lock:
            self._postings.clear()
            self._terms.clear()
            self._doc_of.clear()
            self._lengths.clear()
            self._total_length = 0
            for chunk in chunks:
                self.add(chunk.id, chunk.doc_id, chunk.text)

    def search(
        self, query: str, k: int, allowed_docs: Optional[set[str]] = None
    ) -> list[tuple[str, float]]:
        with self._lock:
            total = len(self._lengths)
            if total == 0:
                return []
            average = self._total_length / total or 1.0
            scores: dict[str, float] = {}
            for term in set(tokenize(query)):
                postings = self._postings.get(term)
                if not postings:
                    continue
                idf = math.log(1 + (total - len(postings) + 0.5) / (len(postings) + 0.5))
                for chunk_id, tf in postings.items():
                    if allowed_docs is not None and self._doc_of[chunk_id] not in allowed_docs:
                        continue
                    length = self._lengths[chunk_id]
                    denominator = tf + self.k1 * (1 - self.b + self.b * length / average)
                    scores[chunk_id] = scores.get(chunk_id, 0.0) + idf * tf * (self.k1 + 1) / denominator
            ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
            return ranked[:k]
