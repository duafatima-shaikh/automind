from typing import Iterator, Sequence

from automind.generation.llm_client import LLMClient
from automind.generation.pipeline import GenerationPipeline
from automind.retrieval.retriever import RetrievedChunk
from automind.store.metadata_store import StoredChunk


class FakeLLM(LLMClient):
    name = "fake"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls = 0

    def generate(self, system, user, *, question="", sources: Sequence = ()) -> str:
        self.calls += 1
        return self.reply

    def stream(self, system, user, *, question="", sources: Sequence = ()) -> Iterator[str]:
        self.calls += 1
        yield from (self.reply[:10], self.reply[10:])


def chunk(text="The monthly pass costs 18 dollars."):
    return RetrievedChunk(StoredChunk("d:0", "d", "f.txt", 1, 0, text), 1.0)


def test_invalid_citations_are_removed(settings):
    llm = FakeLLM("The monthly pass costs 18 dollars [1][4].")
    answer = GenerationPipeline(settings, llm).answer("How much is the monthly pass?", [chunk()])
    assert answer.found and "[4]" not in answer.text and "[1]" in answer.text
    assert answer.removed_citations == [4]


def test_not_found_reply_is_recognised(settings):
    llm = FakeLLM("I could not find the answer in the uploaded documents.")
    answer = GenerationPipeline(settings, llm).answer("How much is the monthly pass?", [chunk()])
    assert answer.found is False


def test_unrelated_question_never_reaches_the_model(settings):
    llm = FakeLLM("anything")
    answer = GenerationPipeline(settings, llm).answer("Who painted the Mona Lisa?", [chunk()])
    assert not answer.found and llm.calls == 0


def test_repeated_question_uses_cache_and_stream_matches(settings):
    llm = FakeLLM("The monthly pass costs 18 dollars [1].")
    pipeline = GenerationPipeline(settings, llm)
    first = pipeline.answer("How much is the monthly pass?", [chunk()])
    second = pipeline.answer("How much is the monthly pass?", [chunk()])
    assert not first.cached and second.cached and llm.calls == 1
    events = list(pipeline.answer_stream("How much is the monthly pass?", [chunk()]))
    assert events[-1]["type"] == "final" and events[-1]["answer"].text == first.text
