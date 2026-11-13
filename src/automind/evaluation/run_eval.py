"""Measure retrieval and answer quality on a golden question set.

Run:  python -m automind.evaluation.run_eval
      python -m automind.evaluation.run_eval --docs my_docs/ --golden my_golden.json
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from typing import Optional

from ..config import Settings
from ..retrieval.retriever import RetrievalOptions
from ..services import Services
from . import metrics as m

DATASETS = Path(__file__).parent / "datasets"

CONFIGURATIONS: dict[str, RetrievalOptions] = {
    "vector only": RetrievalOptions(True, False, False, False),
    "keyword only": RetrievalOptions(False, True, False, False),
    "hybrid": RetrievalOptions(True, True, False, False),
    "hybrid + rerank": RetrievalOptions(True, True, True, False),
    "hybrid + rerank + mmr": RetrievalOptions(True, True, True, True),
}


def evaluate(
    settings: Settings,
    docs_dir: Path = DATASETS / "sample_docs",
    golden_path: Path = DATASETS / "golden.json",
    top_k: int = 5,
    with_generation: bool = True,
    work_dir: Optional[Path] = None,
) -> dict:
    questions = json.loads(golden_path.read_text())["questions"]
    answerable = [q for q in questions if q["answerable"]]
    refusals = [q for q in questions if not q["answerable"]]

    with tempfile.TemporaryDirectory() as temporary:
        run_settings = settings.model_copy(update={"data_dir": work_dir or Path(temporary)})
        services = Services(run_settings)
        try:
            for path in sorted(docs_dir.iterdir()):
                if path.is_file():
                    services.ingestion.ingest(path.name, path.read_bytes())

            retrieval_rows = []
            for name, options in CONFIGURATIONS.items():
                ranks, times = [], []
                for q in answerable:
                    started = time.perf_counter()
                    found = services.retriever.retrieve(q["question"], top_k=top_k, options=options)
                    times.append(time.perf_counter() - started)
                    ranks.append(m.first_hit_rank([r.chunk.text for r in found], q["evidence"]))
                retrieval_rows.append({
                    "configuration": name,
                    "hit@1": round(m.hit_at_k(ranks, 1), 3),
                    "hit@3": round(m.hit_at_k(ranks, 3), 3),
                    "hit@5": round(m.hit_at_k(ranks, 5), 3),
                    "mrr": round(m.mean_reciprocal_rank(ranks), 3),
                    **m.latency_summary(times),
                })

            generation = None
            if with_generation:
                correct, grounding, valid_citation, times = [], [], [], []
                for q in answerable:
                    started = time.perf_counter()
                    result = services.answer_question(q["question"], top_k=top_k)
                    times.append(time.perf_counter() - started)
                    answer = result.answer
                    correct.append(answer.found and m.keywords_present(answer.text, q["keywords"]))
                    grounding.append(answer.grounding_score)
                    valid_citation.append(answer.report.ok)
                refused = [
                    not services.answer_question(q["question"], top_k=top_k).answer.found
                    for q in refusals
                ]
                n = len(answerable) or 1
                generation = {
                    "model": services.llm.name,
                    "answer_correct": round(sum(correct) / n, 3),
                    "grounding_score": round(sum(grounding) / n, 3),
                    "valid_citation_rate": round(sum(valid_citation) / n, 3),
                    "refusal_accuracy": round(sum(refused) / len(refused), 3) if refused else None,
                    **m.latency_summary(times),
                }
            return {
                "embedding": services.encoder.name,
                "chunks": services.metadata.count_chunks(),
                "questions": len(questions),
                "top_k": top_k,
                "retrieval": retrieval_rows,
                "generation": generation,
            }
        finally:
            services.close()


def to_markdown(result: dict) -> str:
    lines = [
        f"Embedding model: `{result['embedding']}`. Chunks: {result['chunks']}. "
        f"Questions: {result['questions']}. Top k: {result['top_k']}.",
        "",
        "### Retrieval",
        "",
        "| Configuration | hit@1 | hit@3 | hit@5 | MRR | mean ms | p95 ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in result["retrieval"]:
        lines.append(
            f"| {row['configuration']} | {row['hit@1']} | {row['hit@3']} | {row['hit@5']} | "
            f"{row['mrr']} | {row['mean_ms']} | {row['p95_ms']} |"
        )
    generation = result["generation"]
    if generation:
        lines += [
            "", "### Answers", "",
            "| Measure | Value |", "|---|---|",
            f"| Answer model | {generation['model']} |",
            f"| Answer contains the expected facts | {generation['answer_correct']} |",
            f"| Grounding score (sentences backed by their citation) | {generation['grounding_score']} |",
            f"| Answers with only valid citations | {generation['valid_citation_rate']} |",
            f"| Correctly refused unanswerable questions | {generation['refusal_accuracy']} |",
            f"| Mean latency (ms) | {generation['mean_ms']} |",
            f"| p95 latency (ms) | {generation['p95_ms']} |",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate AutoMind retrieval and answers")
    parser.add_argument("--docs", type=Path, default=DATASETS / "sample_docs")
    parser.add_argument("--golden", type=Path, default=DATASETS / "golden.json")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=300,
                        help="Small chunks suit the tiny sample documents")
    parser.add_argument("--chunk-overlap", type=int, default=60)
    parser.add_argument("--embedding-backend", default=None,
                        help="hash, sentence-transformers or auto (default: your settings)")
    parser.add_argument("--no-generation", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    overrides: dict = {"chunk_size": args.chunk_size, "chunk_overlap": args.chunk_overlap}
    if args.embedding_backend:
        overrides["embedding_backend"] = args.embedding_backend
    settings = Settings(**overrides)
    result = evaluate(settings, args.docs, args.golden, args.top_k, not args.no_generation)
    report = to_markdown(result)
    print(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report)
        print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
