Embedding model: `hash-384`. Chunks: 24. Questions: 17. Top k: 5.

### Retrieval

| Configuration | hit@1 | hit@3 | hit@5 | MRR | mean ms | p95 ms |
|---|---|---|---|---|---|---|
| vector only | 0.8 | 0.867 | 0.867 | 0.833 | 1.74 | 2.04 |
| keyword only | 0.867 | 1.0 | 1.0 | 0.922 | 0.14 | 0.24 |
| hybrid | 0.8 | 0.867 | 1.0 | 0.867 | 0.32 | 0.52 |
| hybrid + rerank | 0.867 | 0.933 | 1.0 | 0.917 | 1.7 | 1.83 |
| hybrid + rerank + mmr | 0.867 | 0.933 | 1.0 | 0.917 | 1.06 | 1.22 |

### Answers

| Measure | Value |
|---|---|
| Answer model | extractive |
| Answer contains the expected facts | 0.933 |
| Grounding score (sentences backed by their citation) | 1.0 |
| Answers with only valid citations | 1.0 |
| Correctly refused unanswerable questions | 1.0 |
| Mean latency (ms) | 2.85 |
| p95 latency (ms) | 2.99 |
