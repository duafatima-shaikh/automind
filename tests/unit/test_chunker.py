import pytest

from automind.ingestion.chunker import chunk_pages
from automind.ingestion.parsers import Page


def test_chunks_respect_size_and_keep_page_numbers():
    text = " ".join(f"This is sentence number {i} about solar panels." for i in range(40))
    chunks = chunk_pages("d1", [Page(1, text), Page(2, "Second page text here.")], 200, 40)
    assert len(chunks) > 3
    assert all(len(c.text) <= 200 + 60 for c in chunks)
    assert chunks[-1].page == 2
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[0].id == "d1:0"


def test_overlap_repeats_text_between_neighbours():
    text = " ".join(f"Sentence {i} is here." for i in range(30))
    chunks = chunk_pages("d", [Page(1, text)], 120, 40)
    first_last = chunks[0].text.split(". ")[-1]
    assert first_last.split(".")[0] in chunks[1].text


def test_very_long_sentence_is_split():
    chunks = chunk_pages("d", [Page(1, "word " * 500)], 100, 10)
    assert len(chunks) > 5
    assert all(len(c.text) <= 100 for c in chunks)


def test_invalid_overlap_is_rejected():
    with pytest.raises(ValueError):
        chunk_pages("d", [Page(1, "hello")], 100, 100)
