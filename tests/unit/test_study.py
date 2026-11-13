import re
from typing import Sequence

import pytest

from automind.generation import study_offline
from automind.generation.llm_client import LLMClient, LLMError
from automind.generation.study import ANSWER_MARKER, Block, StudyError, StudyRequest
from automind.services import Services

DOC = (
    "The Marlow bike share program launched in March 2019 with 400 bicycles and 40 docking "
    "stations. A monthly pass costs 18 dollars and includes unlimited rides of up to 45 minutes. "
    "The busiest station is Central Library, with more than 1,200 trips on a weekday. "
    "Helmets are not required by law but are recommended for all riders."
)


class RecordingLLM(LLMClient):
    name = "recording"

    def __init__(self, reply="Generated study material."):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def generate(self, system, user, *, question="", sources: Sequence = (), temperature=0.0):
        self.calls.append((system, user))
        return self.reply

    def stream(self, system, user, *, question="", sources: Sequence = (), temperature=0.0):
        self.calls.append((system, user))
        yield self.reply[:5]
        yield self.reply[5:]


@pytest.fixture
def services(settings):
    svc = Services(settings)
    yield svc
    svc.close()


def add(services, name="bikes.txt", text=DOC):
    return services.ingestion.ingest(name, text.encode()).document


# ---------------------------------------------------------------- offline engine
def blocks():
    return [Block("d", "bikes.txt", 1, DOC)]


@pytest.mark.parametrize("task", ["summary", "notes", "explain", "quiz", "flashcards",
                                  "assignment", "mid_exam", "final_exam"])
def test_every_offline_task_produces_markdown(task):
    text = study_offline.generate(task, blocks(), topic="monthly pass price")
    assert text.startswith("> ") and len(text) > 100


def test_quiz_answers_match_the_options():
    text = study_offline.generate("quiz", blocks(), count=3)
    questions, answers = text.split(ANSWER_MARKER)
    options = re.findall(r"^\d+\. .*?(?=^\d+\. |\Z)", questions, flags=re.S | re.M)
    assert options
    for number, block in enumerate(options, start=1):
        letter, answer = re.search(rf"^{number}\. \*\*([A-D])\*\* — (.+?) \(p\.", answers,
                                   flags=re.M).groups()
        assert re.search(rf"^\s+- {letter}\) {re.escape(answer)}$", block, flags=re.M)


def test_exam_marks_add_up_to_the_stated_total():
    text = study_offline.generate("mid_exam", blocks() * 1, total_marks=30)
    total = int(re.search(r"Total marks:\*\* (\d+)", text).group(1))
    sections = [int(m) for m in re.findall(r"Section [ABC]: .*?\((\d+) marks\)", text)]
    assert sum(sections) == total and total > 0


def test_output_is_deterministic():
    assert study_offline.generate("quiz", blocks()) == study_offline.generate("quiz", blocks())


def test_urdu_labels_are_used():
    text = study_offline.generate("summary", blocks(), language="ur")
    assert "خلاصہ" in text and "ص 1" in text


def test_explain_reports_when_the_topic_is_missing():
    text = study_offline.generate("explain", blocks(), topic="quantum chromodynamics")
    assert "Nothing about this topic" in text


# ---------------------------------------------------------------- service with a fake model
def test_offline_study_runs_without_a_model(services):
    add(services)
    result = services.study.run_all(StudyRequest(task="summary"))
    assert result["offline"] is True and "Summary" in result["markdown"]
    assert result["sources"][0]["filename"] == "bikes.txt"


def test_no_documents_is_an_error(services):
    with pytest.raises(StudyError):
        services.study.run_all(StudyRequest(task="summary"))


def test_prompt_contains_material_task_and_language(services):
    add(services)
    llm = RecordingLLM()
    services.study.llm = llm
    result = services.study.run_all(StudyRequest(task="quiz", language="ur", count=7,
                                                 difficulty="hard"))
    system, user = llm.calls[-1]
    assert "Urdu" in system and "Marlow bike share" in user
    assert "7 multiple choice" in user and "hard" in user and ANSWER_MARKER in user
    assert result["markdown"] == "Generated study material." and result["offline"] is False


def test_pages_filter_limits_the_material(services):
    from automind.ingestion.chunker import chunk_pages
    from automind.ingestion.parsers import Page

    doc = add(services, "pages.txt", "Alpha beta gamma delta epsilon zeta eta theta iota kappa.")
    second = chunk_pages(doc.id, [Page(2, "Page two talks about lambda mu nu xi omicron pi rho.")],
                         300, 60)
    second[0].id, second[0].index = f"{doc.id}:99", 99
    services.metadata.add_chunks("pages.txt", second)
    llm = RecordingLLM()
    services.study.llm = llm
    services.study.run_all(StudyRequest(task="summary", pages="2"))
    user = llm.calls[-1][1]
    assert "lambda" in user and "Alpha" not in user


def test_topic_search_picks_matching_passages(services):
    add(services)
    add(services, "coffee.txt", "Coffee should be brewed with water at ninety five degrees.")
    llm = RecordingLLM()
    services.study.llm = llm
    services.study.run_all(StudyRequest(task="explain", topic="monthly pass price",
                                        document_ids=None))
    assert "monthly pass" in llm.calls[-1][1]


def test_long_documents_are_read_in_parts_for_summaries(settings, tmp_path):
    settings = settings.model_copy(update={"study_context_chars": 600, "data_dir": tmp_path / "d2"})
    svc = Services(settings)
    try:
        text = " ".join(f"Sentence number {i} explains topic {i} in a few simple words." for i in range(60))
        svc.ingestion.ingest("long.txt", text.encode())
        llm = RecordingLLM("partial notes")
        svc.study.llm = llm
        events = list(svc.study.run(StudyRequest(task="summary")))
        assert any(e["type"] == "status" for e in events)
        assert len(llm.calls) >= 3                       # several parts, then the final summary
        assert "partial notes" in llm.calls[-1][1]       # the summary is built from the notes
        assert events[-1]["type"] == "final"
    finally:
        svc.close()


def test_long_documents_are_sampled_for_quizzes(settings, tmp_path):
    settings = settings.model_copy(update={"study_context_chars": 800, "data_dir": tmp_path / "d3"})
    svc = Services(settings)
    try:
        text = " ".join(f"Sentence number {i} explains topic {i} in a few simple words." for i in range(80))
        svc.ingestion.ingest("long.txt", text.encode())
        llm = RecordingLLM()
        svc.study.llm = llm
        result = svc.study.run_all(StudyRequest(task="quiz"))
        assert result["sampled"] is True
        assert len(llm.calls[-1][1]) < 2500
    finally:
        svc.close()


def test_student_instructions_reach_the_prompt(services):
    add(services)
    llm = RecordingLLM()
    services.study.llm = llm
    services.study.run_all(StudyRequest(task="notes", instructions="keep it very short"))
    assert "keep it very short" in llm.calls[-1][1]


# ---------------------------------------------------------------- choosing the model
def test_switching_models_is_remembered(services, settings):
    assert services.configure_llm({"provider": "extractive"})["real"] is False
    assert (settings.data_dir / "llm_settings.json").exists()


def test_openai_needs_a_key(services):
    with pytest.raises(LLMError):
        services.configure_llm({"provider": "openai", "model": "gpt-4o-mini"})
    assert services.llm.name == "extractive"   # nothing changed


def test_follow_up_question_uses_the_previous_one(services):
    add(services)
    result = services.answer_question(
        "and what about it?", history=[("How much does a monthly pass cost?", "18 dollars")])
    assert result.answer.found
