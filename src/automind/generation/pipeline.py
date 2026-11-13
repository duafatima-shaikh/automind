"""Turn retrieved chunks into a cited answer, and check the citations."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Sequence

from ..config import Settings
from ..retrieval.retriever import RetrievedChunk
from ..utils.text import term_coverage
from .citations import CitationReport, strip_invalid, validate
from .llm_client import LLMClient, ResponseCache
from .prompts import NOT_FOUND_MESSAGE, PROMPT_VERSION, build_user_prompt, system_prompt


@dataclass
class Source:
    number: int
    chunk_id: str
    doc_id: str
    filename: str
    page: int
    text: str
    score: float
    cited: bool = False


@dataclass
class Answer:
    text: str
    found: bool
    sources: list[Source]
    report: CitationReport
    model: str
    prompt_version: str = PROMPT_VERSION
    cached: bool = False
    removed_citations: list[int] = field(default_factory=list)

    @property
    def grounding_score(self) -> float:
        return self.report.grounding_score


class GenerationPipeline:
    def __init__(self, settings: Settings, llm: LLMClient) -> None:
        self.settings = settings
        self.llm = llm
        self.cache = ResponseCache(settings.llm_cache_size)

    # ---- helpers ----
    @staticmethod
    def build_sources(retrieved: Sequence[RetrievedChunk]) -> list[Source]:
        return [
            Source(i, r.chunk.id, r.chunk.doc_id, r.chunk.filename, r.chunk.page,
                   r.chunk.text, round(r.score, 4))
            for i, r in enumerate(retrieved, start=1)
        ]

    def is_answerable(self, question: str, sources: Sequence[Source],
                      alternatives: Sequence[str] = ()) -> bool:
        """True when at least one source shares enough words with the question (or with one of
        its translations in `alternatives`)."""
        if not sources:
            return False
        threshold = self.settings.min_query_overlap
        if threshold <= 0:
            return True
        questions = [question, *alternatives]
        return max(term_coverage(q, s.text) for q in questions for s in sources) >= threshold

    def _finalize(self, raw: str, sources: list[Source], cached: bool) -> Answer:
        raw = raw.strip()
        if raw.startswith(NOT_FOUND_MESSAGE):
            return Answer(NOT_FOUND_MESSAGE, False, sources, CitationReport(), self.llm.name,
                          cached=cached)
        report = validate(raw, [s.text for s in sources])
        text = strip_invalid(raw, len(sources)) if report.invalid else raw
        for source in sources:
            source.cited = source.number in report.valid
        return Answer(text, True, sources, report, self.llm.name, cached=cached,
                      removed_citations=list(report.invalid))

    def _not_found(self, sources: list[Source]) -> Answer:
        return Answer(NOT_FOUND_MESSAGE, False, sources, CitationReport(), self.llm.name)

    # ---- public ----
    def answer(self, question: str, retrieved: Sequence[RetrievedChunk], *,
               language: str = "en", alternatives: Sequence[str] = (),
               history: Sequence[tuple[str, str]] = ()) -> Answer:
        sources = self.build_sources(retrieved)
        if not self.is_answerable(question, sources, alternatives):
            return self._not_found(sources)
        system = system_prompt(language)
        user = build_user_prompt(question, sources, history)
        key = ResponseCache.key(self.llm.name, system, user)
        cached = self.cache.get(key)
        if cached is not None:
            return self._finalize(cached, sources, cached=True)
        raw = self.llm.generate(system, user, question=question, sources=sources)
        self.cache.put(key, raw)
        return self._finalize(raw, sources, cached=False)

    def answer_stream(
        self, question: str, retrieved: Sequence[RetrievedChunk], *,
        language: str = "en", alternatives: Sequence[str] = (),
        history: Sequence[tuple[str, str]] = (),
    ) -> Iterator[dict]:
        """Yields {"type": "token", "text": ...} pieces and then one {"type": "final", ...}."""
        sources = self.build_sources(retrieved)
        if not self.is_answerable(question, sources, alternatives):
            yield {"type": "final", "answer": self._not_found(sources)}
            return
        system = system_prompt(language)
        user = build_user_prompt(question, sources, history)
        key = ResponseCache.key(self.llm.name, system, user)
        cached = self.cache.get(key)
        if cached is not None:
            for word in cached.split(" "):
                yield {"type": "token", "text": word + " "}
            yield {"type": "final", "answer": self._finalize(cached, sources, cached=True)}
            return
        pieces: list[str] = []
        for piece in self.llm.stream(system, user, question=question, sources=sources):
            pieces.append(piece)
            yield {"type": "token", "text": piece}
        raw = "".join(pieces)
        self.cache.put(key, raw)
        yield {"type": "final", "answer": self._finalize(raw, sources, cached=False)}
