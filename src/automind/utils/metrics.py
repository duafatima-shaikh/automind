"""A tiny in memory metrics collector, shown by the /metrics endpoint."""
from __future__ import annotations

import threading
from collections import Counter, defaultdict, deque
from typing import Deque


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


class Metrics:
    def __init__(self, window: int = 1000) -> None:
        self._lock = threading.Lock()
        self._counters: Counter[str] = Counter()
        self._timings: dict[str, Deque[float]] = defaultdict(lambda: deque(maxlen=window))

    def incr(self, name: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe(self, name: str, seconds: float) -> None:
        with self._lock:
            self._timings[name].append(seconds * 1000.0)

    def snapshot(self) -> dict:
        with self._lock:
            timings = {}
            for name, values in self._timings.items():
                data = list(values)
                timings[name] = {
                    "count": len(data),
                    "mean_ms": round(sum(data) / len(data), 2) if data else 0.0,
                    "p50_ms": round(percentile(data, 50), 2),
                    "p95_ms": round(percentile(data, 95), 2),
                }
            return {"counters": dict(self._counters), "timings": timings}
