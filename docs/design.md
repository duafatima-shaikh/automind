# Design decisions

Each section is one decision, why it was made, and what it costs.

## 1. One service object wires everything

`services.py` builds the encoder, stores, retriever, and generator once and hands them to the API. Routes stay thin. Tests build the same object with temporary folders, so the real code path is tested.

## 2. Parsers, chunker, stores, retrieval and generation are separate packages

Each part can be swapped without touching the others. For example, replacing the vector store only means writing a class with the same few methods.

## 3. Chunks follow sentences and never cross pages

Cutting in the middle of a sentence hurts both search and readability. Keeping chunks inside a page means the page number in a citation is always correct. The cost is some uneven chunk sizes. A small overlap carries the end of one chunk into the next so facts at the border are not lost.

## 4. Hybrid search with reciprocal rank fusion

Meaning search finds paraphrases. Keyword search (BM25) finds exact names, numbers and rare words. Reciprocal rank fusion merges the two ranked lists using only ranks, so the two score scales never need to be compared.

## 5. Reranking, then MMR

The reranker looks at the question and each candidate together, which is more precise than comparing vectors. The default reranker is a light word match scorer. A cross encoder can be selected with `AUTOMIND_RERANKER=cross-encoder`. Maximal marginal relevance then removes near duplicates so the prompt contains different pieces of evidence.

## 6. Two ways to say "not found"

First, if the best chunk shares too few of the question's words (`AUTOMIND_MIN_QUERY_OVERLAP`), the language model is never called. This saves cost and prevents confident nonsense. Second, the model is told to reply with a fixed sentence when the sources lack the answer. The first check is word based, so for topics with heavy paraphrasing you may lower the threshold or set it to 0.

## 7. Citations are validated after generation

The prompt asks for `[1]` style citations. Afterwards the code checks that each number exists, removes numbers that do not, and measures support: the share of a sentence's meaningful words that appear in the cited sources. This is reported as the grounding score. It is a simple word overlap check, not proof of truth, but it catches the common failure of citing the wrong passage.

## 8. A provider neutral language model client

Three clients share one interface: extractive (no model), OpenAI compatible, and Ollama. The extractive client quotes sentences from the sources, so it can never invent facts. It keeps the whole project runnable and testable offline.

## 9. Versioned prompts and a response cache

`PROMPT_VERSION` is returned with every answer. Responses are cached by model and exact prompt, so repeating a question over unchanged sources costs nothing. Embeddings are cached on disk by model and text.

## 10. SQLite plus a saved vector file

SQLite stores documents, chunk text, query history and feedback. Vectors are saved in one `.npz` file written atomically. On startup the keyword index is rebuilt from SQLite and orphan vectors are removed. If the embedding model changes, the saved vectors have the wrong size and AutoMind stops with a clear message instead of returning wrong results.

## 11. Duplicate uploads are detected by file hash

Uploading the same file twice returns the existing document instead of indexing it again.

## 12. Streaming uses server sent events

`/query/stream` sends `sources`, many `token`, and one `final` event. The final event carries the cleaned answer, because citation checking can only happen after the full text exists. The chat screen swaps the streamed text for the cleaned text.

## 13. Every file becomes pages of searchable text

Each parser returns a list of pages, and everything after that step is the same for all file types. A page is a PDF page, a slide, a spreadsheet sheet, a book chapter, or an image frame. This keeps citations meaningful: "slides.pptx, page 4" is slide 4.

Spreadsheet rows are rewritten as sentences that repeat the sheet name and column names. A bare row such as "Chair | 49 | 12" cannot be found or understood on its own, but "Sheet Sales, row 3: Product: Chair | Price: 49 | Stock: 12" can.

## 14. Text recognition is optional and layered

Pictures and scanned PDF pages go through text recognition. A page counts as scanned when it has fewer than `AUTOMIND_OCR_MIN_CHARS_PER_PAGE` characters of normal text, so mixed documents are handled page by page. Engines are tried in order (rapidocr, then Tesseract) and the project still installs and runs without any of them. When one is needed but missing, the API answers 501 with the install command instead of failing silently.

## 15. The file type is detected from the contents

The extension is trusted first. If it is missing or unknown, the first bytes decide (PDF, PNG, JPEG, Office zip structure, and so on), and readable text of any kind is accepted as plain text. Real binary data of an unknown kind is rejected with a list of supported types.
