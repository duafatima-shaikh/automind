"""Split pages into overlapping chunks that always end on a sentence boundary.

Chunks never cross a page boundary, so a page number in a citation is always correct.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..utils.text import split_sentences
from .parsers import Page


@dataclass
class Chunk:
    id: str
    doc_id: str
    page: int
    index: int
    text: str


def _hard_split(sentence: str, size: int) -> list[str]:
    """Break a very long sentence on spaces so it fits inside one chunk."""
    words, pieces, current = sentence.split(" "), [], ""
    for word in words:
        if current and len(current) + len(word) + 1 > size:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_pages(doc_id: str, pages: list[Page], chunk_size: int, overlap: int) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")
    chunks: list[Chunk] = []

    def flush(page_number: int, sentences: list[str]) -> None:
        text = " ".join(sentences).strip()
        if text:
            index = len(chunks)
            chunks.append(Chunk(f"{doc_id}:{index}", doc_id, page_number, index, text))

    for page in pages:
        sentences: list[str] = []
        for sentence in split_sentences(page.text):
            if len(sentence) > chunk_size:
                sentences.extend(_hard_split(sentence, chunk_size))
            else:
                sentences.append(sentence)

        current: list[str] = []
        length = 0
        for sentence in sentences:
            if current and length + len(sentence) + 1 > chunk_size:
                flush(page.number, current)
                carry: list[str] = []
                carried = 0
                for previous in reversed(current):
                    if carried + len(previous) + 1 > overlap:
                        break
                    carry.insert(0, previous)
                    carried += len(previous) + 1
                current, length = carry, carried
            current.append(sentence)
            length += len(sentence) + 1
        flush(page.number, current)
    return chunks
