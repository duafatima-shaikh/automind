"""Measure how long ingestion and queries take.
Usage: python scripts/benchmark.py --repeat 50"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path

from automind.config import Settings
from automind.evaluation.run_eval import DATASETS
from automind.services import Services
from automind.utils.metrics import percentile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=30)
    parser.add_argument("--embedding-backend", default=None)
    args = parser.parse_args()
    overrides = {"chunk_size": 300, "chunk_overlap": 60, "llm_cache_size": 0}
    if args.embedding_backend:
        overrides["embedding_backend"] = args.embedding_backend

    questions = [q["question"] for q in
                 json.loads((DATASETS / "golden.json").read_text())["questions"]]
    with tempfile.TemporaryDirectory() as temporary:
        services = Services(Settings(data_dir=Path(temporary), **overrides))
        started = time.perf_counter()
        for path in sorted((DATASETS / "sample_docs").iterdir()):
            services.ingestion.ingest(path.name, path.read_bytes())
        print(f"Ingestion of sample documents: {time.perf_counter() - started:.2f}s")

        times = []
        for i in range(args.repeat):
            started = time.perf_counter()
            services.answer_question(questions[i % len(questions)])
            times.append((time.perf_counter() - started) * 1000)
        print(f"Queries: {len(times)}  mean {sum(times)/len(times):.1f} ms  "
              f"p50 {percentile(times, 50):.1f} ms  p95 {percentile(times, 95):.1f} ms")
        services.close()


if __name__ == "__main__":
    main()
