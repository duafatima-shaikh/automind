# AutoMind

> **Streamlit version:** run `streamlit run streamlit_app.py`. To publish it on Streamlit Community Cloud through GitHub, follow `DEPLOY_STREAMLIT.md`.

AutoMind lets you upload documents and ask questions about them in plain language. Every answer comes with numbered citations that point to the exact passage, file, and page it came from, so you can check the answer yourself.

It reads almost any file, including pictures and scanned pages. It is a complete Retrieval Augmented Generation (RAG) application: file parsing, chunking, embeddings, hybrid search, reranking, citation checking, a FastAPI backend, a Streamlit chat screen, tests, and a measured evaluation.

## What makes it different

1. **Answers are checked, not just generated.** After the model answers, AutoMind verifies that every citation points to a real source, removes any that do not, and scores how well each sentence is backed by the text it cites.
2. **It says "I could not find the answer" instead of guessing.** Questions unrelated to your documents never reach the language model.
3. **Quality is measured.** A built in evaluation compares vector search, keyword search, hybrid search, reranking, and diversity selection on a set of golden questions.
4. **It works with no keys and no downloads.** The default answer engine quotes the best matching sentences with citations. Switch to OpenAI or a local Ollama model with one setting.

## Files it can read

| Kind | Types | What a "page" in a citation means |
|---|---|---|
| Documents | PDF (also scanned), Word (docx, doc), RTF, OpenDocument text, EPUB books | PDF page, book chapter. Word files count as page 1 |
| Presentations | PowerPoint (pptx, ppt), OpenDocument presentations | Slide number. Speaker notes and tables are included |
| Spreadsheets | Excel (xlsx, xls), CSV, TSV, OpenDocument sheets | Sheet number. Each row is saved with its column names, for example "Sheet Sales, row 2: Product: Chair, Price: 49" |
| Images | png, jpg, gif, bmp, tiff, webp | Frame number. Text in the picture is read with text recognition |
| Text and code | txt, Markdown, HTML, JSON, XML, YAML, log files, source code, and any other readable text file | Page 1 |

The type is also detected from the file contents, so a file with a missing or wrong extension still works.

Reading pictures and scanned pages needs a text recognition engine. Install the built in option with `pip install -e ".[ocr]"`. It needs no extra program. For photos and charts that hold little text, set `AUTOMIND_IMAGE_DESCRIPTIONS=true` with an OpenAI key and a vision capable model, and AutoMind will also store a written description of each picture.

The old Microsoft formats (doc, ppt, xls) are converted with LibreOffice. If it is installed on your computer the conversion happens automatically. Otherwise AutoMind tells you to save the file in the newer format. In Docker, build with `INSTALL_LIBREOFFICE=true` to include it.

## Quick start (Windows, macOS, Linux)

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
python -m pip install -e ".[ocr]"  # "ocr" lets it read images and scanned pages
python scripts/ingest_sample.py    # optional: load four sample documents
python -m uvicorn automind.api.main:app --port 8000
```

Open **http://localhost:8000**. The whole app (chat, study tools, reader, settings) is that one page, so there is nothing else to start. `make dev` does the same with auto reload.

For the best accuracy install real embeddings (a few hundred megabytes), then set `AUTOMIND_EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` in `.env` so a question in Urdu can find English text:

```bash
python -m pip install -e ".[ml]"
```

With Docker: `cp .env.example .env && docker compose up --build`, then open http://localhost:8000.

## What the app does

| Screen | What you get |
|---|---|
| **Ask** | Questions with numbered citations. Click a number to see the exact passage. Follow up questions work ("and the second one?"). Type "make notes", "quiz", "mid exam", "summarise pages 3-5" and it switches to the matching study tool. Microphone input and "read answers aloud". |
| **Study tools** | Summary, explain a topic or pages, exam notes, quiz (with a practice mode that marks your answers), flashcards, assignment, mid-term paper, final paper (sections A, B, C with marks, answer key and marking scheme). Options: topic, pages, difficulty, length, number of questions, total marks. Download as Word, print or save as PDF. |
| **Listen & read** | Any document is read aloud sentence by sentence with the sentence highlighted. Pause, skip, speed, voice. |
| **Languages** | The whole screen and every answer can be English, Urdu (اردو) or Sindhi (سنڌي), with right to left layout. |
| **Settings** | Pick the AI model (OpenAI, Google Gemini, Groq, OpenRouter, Claude, Ollama, any OpenAI compatible server) and paste the key. A test message is sent first, and the key is stored only in `data/llm_settings.json` on your computer. |

### Basic mode versus an AI model

Without a key the app runs in **basic mode**: it works offline, never invents anything, and makes summaries, notes, quizzes and papers by choosing and rearranging sentences from your document (fill in the blank questions, "define" and "discuss" questions). Answers stay in the document's own language; only the headings are translated.

With an **AI model** (Settings) you get natural answers, real questions and model answers, output in Urdu or Sindhi whatever the document language is, and questions in one language about a document in another. Gemini and Groq have free tiers that are enough for study use.

### Voice notes

Reading aloud and the microphone use your browser (Chrome or Edge work best), so they need no extra install. Urdu voices exist on most Windows and Android devices. There are almost no Sindhi voices, so Sindhi text is read with an Urdu or Arabic voice if one is installed and the app shows a notice. Microphone input in Urdu works in Chrome and Edge; Sindhi is usually not recognised.

## Choosing a language model

Set these in `.env`:

| Provider | Settings |
|---|---|
| Built in, no model (default) | `AUTOMIND_LLM_PROVIDER=extractive` |
| OpenAI or any compatible service | `AUTOMIND_LLM_PROVIDER=openai`, `AUTOMIND_OPENAI_API_KEY=...`, `AUTOMIND_LLM_MODEL=gpt-4o-mini`, optionally `AUTOMIND_OPENAI_BASE_URL` |
| Local Ollama | `AUTOMIND_LLM_PROVIDER=ollama`, `AUTOMIND_LLM_MODEL=llama3.1`, `AUTOMIND_OLLAMA_URL=http://localhost:11434` |

## Using the API

```bash
curl -F "file=@report.pdf" localhost:8000/upload

curl -X POST localhost:8000/query -H 'content-type: application/json' \
  -d '{"question": "What are the main findings?"}'
```

The response contains the answer, the sources with page numbers, a citation check, and timings. Use `/query/stream` to receive the answer word by word. The full list of endpoints is in `docs/api.md`.

## How it works

```
Upload -> parse -> chunk -> embed -> save (vectors + keyword index + SQLite)

Question -> vector search + keyword search -> merge (reciprocal rank fusion)
         -> rerank -> diversify (MMR) -> prompt -> answer
         -> check citations -> response with sources
```

The design decisions are explained in `docs/design.md`.

## Evaluation results

Measured on the four sample documents (24 chunks, 17 questions, 2 of them unanswerable) with the offline hash encoder and the built in answer engine. Reproduce with `make eval`.

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

These numbers come from a very small test set, so treat them as a demonstration of the method, not a benchmark. With real embeddings and your own documents the picture changes. Add your own questions to a copy of `golden.json` and run:

```bash
python -m automind.evaluation.run_eval --docs my_docs/ --golden my_golden.json
```

See `docs/evaluation.md` for what each number means.

## Project layout

```
src/automind/
  config.py            all settings (environment variables)
  services.py          wires every part together
  api/                 FastAPI app, routes, request and response shapes
  ingestion/           parsers (pdf, office, spreadsheets, images, text), text recognition, chunker, pipeline
  embeddings/          encoders and the embedding cache
  store/               vector store, keyword index, SQLite metadata
  retrieval/           hybrid retriever, reranker, MMR
  generation/          prompts, language model clients, citation checking
  evaluation/          golden questions, metrics, evaluation runner
web/                   the web app (HTML, CSS, JavaScript, translations)
frontend/              old Streamlit screen (not needed any more)
tests/                 unit and integration tests
scripts/               sample loader and benchmark
```

## Development

```bash
make test        # no downloads needed
make lint
make eval
make bench
```

## Known limits

* Pictures placed inside Word, PowerPoint and PDF files are not read, only pictures uploaded as files and fully scanned PDF pages. Charts and diagrams inside documents are ignored.
* Text recognition is slower than normal reading (a few seconds per page) and can misread poor quality scans or handwriting.
* Formulas in Excel files show the value last saved by Excel. A file made by a program that never calculated it may show empty cells.
* Search is a full scan, which is fine up to tens of thousands of chunks. Beyond that, move the vector store to Qdrant or Chroma behind the same interface in `store/vector_store.py`.
* Urdu and Sindhi: text in PDFs is sometimes stored in a broken order by the program that made it; if a PDF looks scrambled, export it again or use the image reader. Reading Urdu or Sindhi from images needs Tesseract with the `urd` and `snd` language packs (the built in reader recognises English and Chinese only).
* There is no login. Put it behind a gateway before sharing it publicly.
* Word files have no page numbers, so all their text is reported as page 1.
* Password protected files cannot be read.
