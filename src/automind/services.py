"""Builds every component once and wires them together. The API talks only to this class."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Iterator, Optional, Sequence

from .config import Settings
from .embeddings.cache import CachedEncoder, EmbeddingCache
from .embeddings.encoder import build_encoder
from .generation.llm_client import LLMClient, LLMError, build_llm
from .generation.pipeline import Answer, GenerationPipeline
from .generation.study import StudyService
from .ingestion.pipeline import IngestionPipeline
from .retrieval.reranker import build_reranker
from .retrieval.retriever import RetrievedChunk, Retriever
from .store.bm25_store import BM25Store
from .store.metadata_store import MetadataStore
from .store.vector_store import VectorStore
from .utils.metrics import Metrics
from .utils.text import merge_overlapping, tokenize

logger = logging.getLogger(__name__)

LLM_SETTINGS_FILE = "llm_settings.json"
PROVIDERS = ("extractive", "openai", "ollama")


@dataclass
class Retrieval:
    chunks: list
    seconds: float
    alternatives: list  # other phrasings of the question used for the "is it answerable" check
    question: str       # the question text to give the answer engine


@dataclass
class QueryResult:
    query_id: str
    answer: Answer
    timings_ms: dict


class Services:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = Metrics()
        self.write_lock = threading.RLock()

        self.metadata = MetadataStore(settings.data_dir / "metadata.db")
        base_encoder = build_encoder(settings)
        self._embedding_cache: Optional[EmbeddingCache] = None
        if settings.embedding_cache:
            self._embedding_cache = EmbeddingCache(settings.data_dir / "embedding_cache.db")
            self.encoder = CachedEncoder(base_encoder, self._embedding_cache)
        else:
            self.encoder = base_encoder

        self.vectors = VectorStore(self.encoder.dim, settings.data_dir / "vectors.npz",
                                   use_faiss=settings.use_faiss)
        self._reconcile()
        self.bm25 = BM25Store()
        self.bm25.rebuild(self.metadata.iter_chunks())

        self.reranker = build_reranker(settings)
        self.retriever = Retriever(settings, self.encoder, self.vectors, self.bm25,
                                   self.metadata, self.reranker)
        self.llm = build_llm(settings)
        self.generator = GenerationPipeline(settings, self.llm)
        self.study = StudyService(settings, self.metadata, self.retriever, self.llm)
        self.ingestion = IngestionPipeline(settings, self.metadata, self.encoder, self.vectors,
                                           self.bm25, self.write_lock)
        self._load_saved_llm()

    # ---- choosing the answer model while the app runs ----
    def _llm_file(self):
        return self.settings.data_dir / LLM_SETTINGS_FILE

    def _load_saved_llm(self) -> None:
        """A model chosen in the Settings screen is remembered between restarts."""
        path = self._llm_file()
        if not path.exists():
            return
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            settings, llm = self._build(saved)
            self._swap_llm(settings, llm)
        except Exception as error:  # noqa: BLE001
            logger.warning("Ignoring saved model settings (%s)", error)

    def _build(self, config: dict) -> tuple[Settings, LLMClient]:
        provider = config.get("provider", "extractive")
        if provider not in PROVIDERS:
            raise LLMError(f"Unknown provider: {provider}")
        updates: dict = {"llm_provider": provider}
        for field, key in (("llm_model", "model"), ("openai_base_url", "base_url"),
                           ("openai_api_key", "api_key"), ("ollama_url", "ollama_url")):
            if config.get(key):
                updates[field] = config[key]
        settings = self.settings.model_copy(update=updates)
        return settings, build_llm(settings)

    def _swap_llm(self, settings: Settings, llm: LLMClient) -> None:
        self.settings = settings
        self.llm = llm
        self.generator.llm = llm
        self.study.llm = llm

    def configure_llm(self, config: dict, test: bool = True) -> dict:
        """Switch the answer model. Raises LLMError (and changes nothing) if it does not work."""
        settings, llm = self._build(config)
        if test and llm.is_real_model:
            llm.generate("You are a connection test.", "Reply with the single word OK.",
                         temperature=0.0)
        self._swap_llm(settings, llm)
        saved = {k: v for k, v in config.items() if v}
        if saved.get("provider") == "openai" and "api_key" not in saved and settings.openai_api_key:
            saved["api_key"] = settings.openai_api_key
        path = self._llm_file()
        path.write_text(json.dumps(saved), encoding="utf-8")
        try:
            os.chmod(path, 0o600)  # the file can hold an API key
        except OSError:
            pass
        return self.llm_status()

    def llm_status(self) -> dict:
        return {
            "provider": self.settings.llm_provider,
            "model": self.settings.llm_model,
            "name": self.llm.name,
            "real": self.llm.is_real_model,
            "base_url": self.settings.openai_base_url,
            "ollama_url": self.settings.ollama_url,
            "has_key": bool(self.settings.openai_api_key),
            "embedding": self.encoder.name,
            "semantic_search": not self.encoder.name.startswith("hash"),
        }

    def _reconcile(self) -> None:
        """Drop vectors whose chunk no longer exists (for example after a crash)."""
        known = {c.id for c in self.metadata.iter_chunks()}
        stale = [cid for cid in self.vectors.ids if cid not in known]
        if stale:
            logger.warning("Removing %d orphan vectors", len(stale))
            self.vectors.delete(stale)
            self.vectors.save()

    # ---- queries ----
    def _retrieve(self, question: str, top_k: Optional[int],
                  document_ids: Optional[Sequence[str]],
                  history: Sequence[tuple[str, str]] = ()) -> Retrieval:
        """Find the passages for a question.

        A short follow up like "and the second one?" is searched together with the previous
        question. If nothing matches and a real language model is connected, the question is
        translated (English and Urdu) and searched again, so a question in Urdu can find
        English text and the other way round."""
        started = time.perf_counter()
        query = question
        if history and len(tokenize(question)) < 4:
            query = f"{history[-1][0]} {question}"
        retrieved = self.retriever.retrieve(query, top_k=top_k, document_ids=document_ids)
        alternatives: list[str] = [query] if query != question else []
        if self.llm.is_real_model:
            sources = self.generator.build_sources(retrieved)
            if not self.generator.is_answerable(query, sources):
                translations = self._translations(question)
                if translations:
                    alternatives += translations
                    retrieved = self.retriever.retrieve(
                        " ".join([query, *translations]), top_k=top_k, document_ids=document_ids)
        elapsed = time.perf_counter() - started
        self.metrics.observe("retrieval", elapsed)
        # A real model sees the earlier turns in its prompt. The built in engine does not, so it
        # is given the combined question instead.
        asked = question if self.llm.is_real_model else query
        return Retrieval(retrieved, elapsed, alternatives, asked)

    def _translations(self, question: str) -> list[str]:
        try:
            text = self.llm.generate(
                "You translate search questions. Output only the translations, one per line, "
                "with no numbering and no comments.",
                f"Translate this question into English on the first line and into Urdu on the "
                f"second line:\n{question}", temperature=0.0)
        except LLMError:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()][:2]

    def _record(self, query_id: str, question: str, answer: Answer) -> None:
        self.metadata.log_query(query_id, question, answer.text, answer.found)
        self.metrics.incr("queries_total")
        self.metrics.incr("answers_found" if answer.found else "answers_not_found")
        if answer.removed_citations:
            self.metrics.incr("invalid_citations_removed", len(answer.removed_citations))

    def answer_question(self, question: str, top_k: Optional[int] = None,
                        document_ids: Optional[Sequence[str]] = None, language: str = "en",
                        history: Sequence[tuple[str, str]] = ()) -> QueryResult:
        found = self._retrieve(question, top_k, document_ids, history)
        retrieval_time = found.seconds
        started = time.perf_counter()
        answer = self.generator.answer(found.question, found.chunks, language=language,
                                       alternatives=found.alternatives, history=history)
        generation_time = time.perf_counter() - started
        self.metrics.observe("generation", generation_time)
        query_id = uuid.uuid4().hex
        self._record(query_id, question, answer)
        return QueryResult(query_id, answer, {
            "retrieval": round(retrieval_time * 1000, 2),
            "generation": round(generation_time * 1000, 2),
        })

    def stream_question(self, question: str, top_k: Optional[int] = None,
                        document_ids: Optional[Sequence[str]] = None, language: str = "en",
                        history: Sequence[tuple[str, str]] = ()) -> Iterator[dict]:
        found = self._retrieve(question, top_k, document_ids, history)
        retrieval_time = found.seconds
        yield {"type": "sources", "sources": self.generator.build_sources(found.chunks)}
        started = time.perf_counter()
        for event in self.generator.answer_stream(found.question, found.chunks, language=language,
                                                  alternatives=found.alternatives,
                                                  history=history):
            if event["type"] == "token":
                yield event
                continue
            generation_time = time.perf_counter() - started
            self.metrics.observe("generation", generation_time)
            query_id = uuid.uuid4().hex
            self._record(query_id, question, event["answer"])
            yield {"type": "final", "query_id": query_id, "answer": event["answer"],
                   "timings_ms": {"retrieval": round(retrieval_time * 1000, 2),
                                  "generation": round(generation_time * 1000, 2)}}

    # ---- reading a document back (for the reader and read aloud) ----
    def document_pages(self, doc_id: str) -> Optional[list[dict]]:
        if self.metadata.get_document(doc_id) is None:
            return None
        pages: dict[int, list[str]] = {}
        for chunk in self.metadata.get_document_chunks(doc_id):
            pages.setdefault(chunk.page, []).append(chunk.text)
        return [{"page": number, "text": merge_overlapping(texts)}
                for number, texts in sorted(pages.items())]

    def close(self) -> None:
        self.vectors.save()
        self.metadata.close()
        if self._embedding_cache:
            self._embedding_cache.close()
