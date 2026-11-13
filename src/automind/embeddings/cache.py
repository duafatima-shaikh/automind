"""Remember embeddings already computed, so uploading the same text twice costs nothing."""
from __future__ import annotations

import hashlib
import sqlite3
import threading
from pathlib import Path
from typing import Sequence

import numpy as np

from .encoder import Encoder


class EmbeddingCache:
    def __init__(self, path: Path) -> None:
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector BLOB NOT NULL)"
        )
        self._db.commit()

    def get_many(self, keys: Sequence[str]) -> dict[str, np.ndarray]:
        found: dict[str, np.ndarray] = {}
        with self._lock:
            for key in keys:
                row = self._db.execute(
                    "SELECT vector FROM embeddings WHERE key = ?", (key,)
                ).fetchone()
                if row:
                    found[key] = np.frombuffer(row[0], dtype=np.float32)
        return found

    def put_many(self, items: dict[str, np.ndarray]) -> None:
        with self._lock:
            self._db.executemany(
                "INSERT OR REPLACE INTO embeddings (key, vector) VALUES (?, ?)",
                [(k, v.astype(np.float32).tobytes()) for k, v in items.items()],
            )
            self._db.commit()

    def close(self) -> None:
        with self._lock:
            self._db.close()


class CachedEncoder:
    def __init__(self, inner: Encoder, cache: EmbeddingCache) -> None:
        self.inner = inner
        self.cache = cache
        self.name = inner.name
        self.dim = inner.dim
        self.hits = 0
        self.misses = 0

    def _key(self, text: str) -> str:
        return hashlib.sha256(f"{self.name}\n{text}".encode("utf-8")).hexdigest()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        keys = [self._key(t) for t in texts]
        cached = self.cache.get_many(keys)
        missing = [i for i, k in enumerate(keys) if k not in cached]
        self.hits += len(texts) - len(missing)
        self.misses += len(missing)
        if missing:
            fresh = self.inner.encode([texts[i] for i in missing])
            self.cache.put_many({keys[i]: fresh[n] for n, i in enumerate(missing)})
            for n, i in enumerate(missing):
                cached[keys[i]] = fresh[n]
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([cached[k] for k in keys]).astype(np.float32)
