# How quality is measured

Run `make eval` or `python -m automind.evaluation.run_eval`.

## The golden set

`src/automind/evaluation/datasets/golden.json` holds questions. Each has:

* `question`: what a user would ask.
* `evidence`: a phrase that must appear in a retrieved chunk for retrieval to count as correct.
* `keywords`: words the answer must contain.
* `answerable`: false for questions the documents cannot answer. These should be refused.

To test your own documents, write 30 or more questions like these and pass `--docs` and `--golden`.

## Retrieval numbers

* **hit@k**: the share of questions where a chunk containing the evidence appears in the top k results.
* **MRR** (mean reciprocal rank): the average of 1 divided by the rank of the first correct chunk. 1.0 means the right chunk is always first.
* **mean ms and p95 ms**: average time, and the time that 95 percent of searches beat.

Five settings are compared so you can see whether each added step helps: vector only, keyword only, hybrid, hybrid with rerank, and hybrid with rerank and MMR.

## Answer numbers

* **Answer contains the expected facts**: the keywords appear in the answer.
* **Grounding score**: the share of answer sentences that have a valid citation and whose words are mostly found in the cited text.
* **Answers with only valid citations**: no citation number pointed to a missing source.
* **Correctly refused**: unanswerable questions that received the "could not find" reply.

## Reading the results honestly

* A small test set gives rough numbers. Moving one question changes hit@1 by several points.
* The hash encoder matches words, not meaning. Real embeddings should do better on paraphrased questions.
* The grounding score is word overlap, so it can miss a wrong citation that happens to share many words. For high stakes use, add a human reviewed sample.
