"""Stores one normalised vector per chunk and finds the closest ones.

Uses FAISS when it is installed. Otherwise it uses plain numpy, which is fast enough for
tens of thousands of chunks.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)


class VectorStore:
    def __init__(self, dim: int, path: Optional[Path] = None, use_faiss: bool = True) -> None:
        self.dim = dim
        self.path = path
        self._lock = threading.RLock()
        self._ids: list[str] = []
        self._matrix = np.zeros((0, dim), dtype=np.float32)
        self._faiss = None
        self._faiss_module = None
        self._dirty = True
        if use_faiss:
            try:
                import faiss  # type: ignore

                self._faiss_module = faiss
            except ImportError:
                logger.info("faiss is not installed, using numpy for vector search")
        if path is not None and path.exists():
            self._load()

    def __len__(self) -> int:
        return len(self._ids)

    @property
    def ids(self) -> list[str]:
        return list(self._ids)

    def add(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        if len(ids) == 0:
            return
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dim or len(ids) != vectors.shape[0]:
            raise ValueError(f"Expected {len(ids)} vectors of size {self.dim}")
        with self._lock:
            self._ids.extend(ids)
            self._matrix = np.vstack([self._matrix, vectors])
            self._dirty = True

    def delete(self, ids: Sequence[str]) -> None:
        remove = set(ids)
        with self._lock:
            keep = [i for i, cid in enumerate(self._ids) if cid not in remove]
            self._ids = [self._ids[i] for i in keep]
            self._matrix = self._matrix[keep] if keep else np.zeros((0, self.dim), np.float32)
            self._dirty = True

    def _build_faiss(self) -> None:
        if self._faiss_module is None:
            return
        index = self._faiss_module.IndexFlatIP(self.dim)
        if len(self._ids):
            index.add(self._matrix)
        self._faiss = index
        self._dirty = False

    def search(
        self, query: np.ndarray, k: int, allowed: Optional[set[str]] = None
    ) -> list[tuple[str, float]]:
        with self._lock:
            if not self._ids:
                return []
            query = np.asarray(query, dtype=np.float32).reshape(1, -1)
            if self._faiss_module is not None and allowed is None:
                if self._dirty or self._faiss is None:
                    self._build_faiss()
                scores, positions = self._faiss.search(query, min(k, len(self._ids)))
                return [
                    (self._ids[p], float(s))
                    for s, p in zip(scores[0], positions[0]) if p >= 0
                ]
            scores = (self._matrix @ query[0]).astype(np.float32)
            if allowed is not None:
                mask = np.array([cid in allowed for cid in self._ids])
                scores = np.where(mask, scores, -np.inf)
            order = np.argsort(-scores)[:k]
            return [(self._ids[i], float(scores[i])) for i in order if np.isfinite(scores[i])]

    def get(self, ids: Sequence[str]) -> dict[str, np.ndarray]:
        with self._lock:
            position = {cid: i for i, cid in enumerate(self._ids)}
            return {cid: self._matrix[position[cid]] for cid in ids if cid in position}

    def save(self) -> None:
        if self.path is None:
            return
        with self._lock:
            temporary = self.path.with_name(self.path.stem + ".tmp.npz")
            np.savez(temporary, ids=np.array(self._ids, dtype=str), matrix=self._matrix,
                     dim=np.array([self.dim]))
            os.replace(temporary, self.path)

    def _load(self) -> None:
        data = np.load(self.path, allow_pickle=False)
        stored_dim = int(data["dim"][0])
        if stored_dim != self.dim:
            raise ValueError(
                f"The saved vectors have size {stored_dim} but the current encoder produces "
                f"size {self.dim}. Delete {self.path} and re-upload your documents, or switch "
                "back to the previous embedding model."
            )
        self._ids = [str(i) for i in data["ids"].tolist()]
        self._matrix = data["matrix"].astype(np.float32)
        self._dirty = True
