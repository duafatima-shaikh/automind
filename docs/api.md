# API summary

Interactive documentation is served at `/docs` (OpenAPI). The raw schema is at `/openapi.json`.

| Method and path | Purpose |
|---|---|
| `POST /upload` | Upload a file (`multipart/form-data`, field `file`): PDF, Word, PowerPoint, Excel, CSV, OpenDocument, RTF, EPUB, HTML, text and code files, or an image. Returns the document. 201 for new, 200 if the same file was uploaded before. 415 unsupported type, 422 unreadable or no text found, 413 too large, 501 text recognition needed but not installed. |
| `GET /documents` | List documents. |
| `GET /documents/{id}` | One document, or 404. |
| `DELETE /documents/{id}` | Remove a document with its chunks and vectors. 204 or 404. |
| `POST /query` | Ask a question. Body: `question`, optional `top_k` (1 to 20), optional `document_ids`, `language` (en, ur, sd), `history` (earlier question and answer pairs). |
| `POST /query/stream` | Same input. Server sent events: `sources`, `token` (many), `final`, `error`. |
| `POST /feedback` | Body: `query_id`, `helpful`, optional `comment`. 404 for an unknown query. |
| `POST /study` | Make study material. Body: `task` (summary, explain, notes, quiz, flashcards, assignment, mid_exam, final_exam), optional `document_ids`, `topic`, `pages` ("3-5, 8"), `instructions`, `language` (en, ur, sd), `difficulty`, `length`, `count`, `total_marks`. Returns Markdown. Everything after the line `---ANSWERS---` is the answer key. |
| `POST /study/stream` | Same input. Server sent events: `meta`, `status`, `token` (many), `final`, `error`. |
| `GET /documents/{id}/text` | The text of a document page by page. |
| `GET /settings/llm`, `POST /settings/llm` | Show or change the answer model. The key is never returned. A test message is sent before saving (400 if it fails). |
| `POST /export/docx` | Body: `markdown`, `title`, `language`. Returns a Word file. |
| `GET /health` | Status, version, counts, embedding model, answer model. |
| `GET /metrics` | Counters, latency percentiles, index sizes, feedback totals, embedding cache hits. |

## Query response

```json
{
  "query_id": "9f2c...",
  "answer": "A monthly pass costs 18 dollars [1].",
  "found": true,
  "sources": [
    {"number": 1, "filename": "bikes.txt", "page": 1, "text": "...", "score": 1.0, "cited": true}
  ],
  "citation_check": {"valid": [1], "removed": [], "grounding_score": 1.0},
  "model": "extractive",
  "prompt_version": "v1",
  "cached": false,
  "timings_ms": {"retrieval": 3.1, "generation": 0.8}
}
```

`found: false` means the documents did not contain the answer. `citation_check.removed` lists citation numbers the model invented, which were stripped from the answer.
