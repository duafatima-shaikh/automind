"""Check that every citation in an answer points at a real source, and that the cited
source really supports the sentence."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from ..utils.text import content_terms, split_sentences

_CITATION_GROUP = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
SUPPORT_THRESHOLD = 0.5
_TRAILING = re.compile(r"([.!?])\s*((?:\[\d+(?:\s*,\s*\d+)*\]\s*)+)")


def _attach_citations(text: str) -> str:
    """Models often write 'Sentence. [1]'. Move the citation inside the sentence."""
    return _TRAILING.sub(lambda m: f" {m.group(2).strip()}{m.group(1)} ", text)


@dataclass
class CitationReport:
    valid: list[int] = field(default_factory=list)
    invalid: list[int] = field(default_factory=list)
    sentences: int = 0
    cited_sentences: int = 0
    supported_sentences: int = 0

    @property
    def grounding_score(self) -> float:
        """Share of sentences that carry a valid citation AND are backed by the cited text."""
        return self.supported_sentences / self.sentences if self.sentences else 0.0

    @property
    def ok(self) -> bool:
        return not self.invalid and bool(self.valid)


def extract_citations(text: str) -> list[int]:
    numbers: list[int] = []
    for group in _CITATION_GROUP.findall(text):
        numbers.extend(int(n) for n in re.split(r"\s*,\s*", group))
    return numbers


def strip_invalid(text: str, source_count: int) -> str:
    """Remove citation numbers that do not match any source."""

    def replace(match: re.Match) -> str:
        kept = [n for n in re.split(r"\s*,\s*", match.group(1)) if 1 <= int(n) <= source_count]
        return f"[{', '.join(kept)}]" if kept else ""

    cleaned = _CITATION_GROUP.sub(replace, text)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def validate(answer: str, source_texts: Sequence[str]) -> CitationReport:
    """source_texts[0] is source number 1, and so on."""
    count = len(source_texts)
    cited = extract_citations(answer)
    report = CitationReport(
        valid=sorted({n for n in cited if 1 <= n <= count}),
        invalid=sorted({n for n in cited if not 1 <= n <= count}),
    )
    for sentence in split_sentences(_attach_citations(answer)):
        numbers = [n for n in extract_citations(sentence) if 1 <= n <= count]
        report.sentences += 1
        if not numbers:
            continue
        report.cited_sentences += 1
        sentence_terms = set(content_terms(_CITATION_GROUP.sub("", sentence)))
        if not sentence_terms:
            continue
        source_terms: set[str] = set()
        for n in numbers:
            source_terms |= set(content_terms(source_texts[n - 1]))
        if len(sentence_terms & source_terms) / len(sentence_terms) >= SUPPORT_THRESHOLD:
            report.supported_sentences += 1
    return report
