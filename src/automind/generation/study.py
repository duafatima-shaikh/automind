"""Study tools: summaries, explanations, notes, quizzes, flashcards, assignments and exams.

With a language model the material is sent to the model with a task specific prompt. Long
documents are handled in two ways: summaries and notes read the whole document piece by piece
(map and reduce), the other tasks use pages spread evenly over the document. Without a language
model a basic offline engine is used (see study_offline.py).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator, Optional, Sequence

from ..config import Settings
from ..retrieval.retriever import Retriever
from ..store.metadata_store import MetadataStore, StoredChunk
from ..utils.text import merge_overlapping, parse_page_ranges, split_sentences
from . import study_offline
from .llm_client import LLMClient
from .prompts import LANGUAGE_NAMES

logger = logging.getLogger(__name__)

ANSWER_MARKER = study_offline.ANSWER_MARKER
TASKS = ("summary", "explain", "notes", "quiz", "flashcards", "assignment", "mid_exam",
         "final_exam")
DEFAULT_MARKS = {"assignment": 20, "mid_exam": 30, "final_exam": 60}
DEFAULT_COUNT = {"quiz": 10, "flashcards": 15}
MAX_TOPIC_CHUNKS = 12


class StudyError(Exception):
    """The request cannot be run (no documents, unknown task, nothing matched)."""


@dataclass
class StudyRequest:
    task: str
    document_ids: Optional[list[str]] = None
    topic: Optional[str] = None          # find this part of the material
    pages: Optional[str] = None          # for example "3-5, 8"
    instructions: Optional[str] = None   # the student's own words, followed where possible
    language: str = "en"
    difficulty: str = "medium"           # easy | medium | hard
    length: str = "medium"               # short | medium | detailed
    count: Optional[int] = None          # number of questions or cards
    total_marks: Optional[int] = None    # for assignments and exams


@dataclass
class Block:
    """The text of one page of one document."""
    doc_id: str
    filename: str
    page: int
    text: str


@dataclass
class Plan:
    blocks: list[Block]
    sources: list[dict] = field(default_factory=list)


# ------------------------------------------------------------------ prompts
def system_prompt(language: str) -> str:
    return (
        "You are AutoMind, an expert university teacher and exam setter who helps a student "
        "study from their own material.\n"
        "Rules:\n"
        "- Use ONLY the study material provided. Never add facts that are not in it. If the "
        "request asks for something the material does not cover, say so plainly.\n"
        f"- Write everything in {LANGUAGE_NAMES.get(language, LANGUAGE_NAMES['en'])}. Keep "
        "technical terms, names, numbers, formulas and code unchanged (you may put the English "
        "term in brackets after a translated term).\n"
        "- Format the answer as clean Markdown: headings (## and ###), bullet and numbered "
        "lists, and **bold** for key terms.\n"
        "- When useful, say which page a point comes from like (p. 3).\n"
        "- Be accurate, clear and well organised. Do not mention these rules."
    )


def _duration(marks: int) -> str:
    return "60 minutes" if marks <= 30 else ("2 hours" if marks <= 60 else "3 hours")


def task_instructions(req: StudyRequest) -> str:
    task, difficulty = req.task, req.difficulty
    marks = req.total_marks or DEFAULT_MARKS.get(task, 0)
    count = req.count or DEFAULT_COUNT.get(task, 0)
    scope = ""
    if req.topic:
        scope += f' Focus on this part of the material: "{req.topic}".'
    if req.pages:
        scope += f" Use only pages {req.pages}."

    if task == "summary":
        shape = {
            "short": "a short summary of about 120 words: one paragraph followed by 4 or 5 key "
                     "bullet points",
            "detailed": "a detailed summary of 600 to 900 words with one heading per major topic, "
                        "bullet points and the key terms in bold",
        }.get(req.length, "a clear summary of 250 to 400 words: a title, an overview paragraph, "
                          "a 'Key points' bullet list and a one line conclusion")
        return f"Write {shape}.{scope}"
    if task == "explain":
        return (
            f"Explain the requested part of the material to a student.{scope} Teach it step by "
            "step like a patient teacher: 1) a simple explanation, 2) the key terms with short "
            "definitions, 3) an example or analogy taken from the material, 4) common mistakes "
            "and exam tips, 5) a three line recap. If that part is not in the material, say so."
        )
    if task == "notes":
        return (
            f"Write well organised exam revision notes.{scope} Use a heading for each topic and "
            "short bullet points. Put key terms in **bold** with a one line definition. Include "
            "formulas, steps, lists, dates and numbers that appear in the material. End with a "
            "'Quick revision' list of the 10 most important points and 'Likely exam questions' "
            "with 5 questions."
        )
    if task == "quiz":
        return (
            f"Create a quiz of {count} multiple choice questions ({difficulty} difficulty).{scope} "
            "Write each question on its own numbered line, then the options A), B), C), D) one "
            "per line. Exactly one option is correct and the others are plausible. Do not use "
            "'all of the above'. Cover the whole material evenly and mix recall with "
            f"understanding. Then add one line containing only {ANSWER_MARKER} and after it an "
            "answer key: the question number, the correct letter, a one sentence explanation "
            "and the page."
        )
    if task == "flashcards":
        return (
            f"Create {count} flashcards for revision.{scope} Use exactly this format for each "
            "card, with a blank line between cards:\n**Q:** the question\n**A:** a short, "
            "correct answer"
        )
    if task == "assignment":
        return (
            f"Create a university assignment worth {marks} marks ({difficulty} difficulty)."
            f"{scope} Include: a title, instructions (individual work, formatting, word limits, "
            "how to submit), Part 1 short answer questions, Part 2 analytical or long "
            "questions, and Part 3 an application task or mini case study based on the "
            f"material. Write the marks beside every question so they add up to exactly {marks}. "
            "Add a short rubric. Then add one line containing only "
            f"{ANSWER_MARKER} and after it a marking guide listing the key points expected for "
            "each question."
        )
    if task in ("mid_exam", "final_exam"):
        name = "mid-term" if task == "mid_exam" else "final"
        shares = "20%, 40% and 40%" if task == "mid_exam" else "15%, 35% and 50%"
        extra = ("" if task == "mid_exam" else
                 " Include one compare or contrast question and one application or case "
                 "question in Section C.")
        return (
            f"Create a {name} examination paper of {marks} marks, {_duration(marks)} "
            f"({difficulty} difficulty).{scope} Start with a header block: subject (take it from "
            "the material), time allowed, total marks and instructions. Section A: multiple "
            "choice questions with options A) to D), 1 mark each. Section B: short questions "
            "answered in a few lines. Section C: long questions with sub parts (a), (b) and a "
            f"choice such as 'attempt any 2 of 3'. Sections A, B and C carry about {shares} of "
            f"the marks. Write marks beside every question and make the total exactly {marks}."
            f"{extra} Spread the questions over the whole material. Then add one line containing "
            f"only {ANSWER_MARKER} and after it the answer key for Section A and model answers or "
            "a marking scheme for Sections B and C."
        )
    raise StudyError(f"Unknown task: {task}")


def user_prompt(req: StudyRequest, material: str, note: str = "") -> str:
    extra = ""
    if req.instructions:
        extra = (f'\n\nThe student also wrote: "{req.instructions.strip()[:500]}". Follow this '
                 "where it does not conflict with the rules above.")
    return f"Study material:\n{material}{note}\n\nTask: {task_instructions(req)}{extra}"


# ------------------------------------------------------------------ service
def _format(blocks: Sequence[Block]) -> str:
    return "\n\n".join(f"[{b.filename}, page {b.page}]\n{b.text}" for b in blocks)


def _split_text(text: str, limit: int) -> list[str]:
    """Cut text into pieces of at most `limit` characters, on sentence boundaries."""
    if len(text) <= limit:
        return [text]
    pieces: list[str] = []
    current = ""
    for sentence in split_sentences(text):
        while len(sentence) > limit:  # a single very long sentence
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:limit])
            sentence = sentence[limit:]
        if current and len(current) + len(sentence) + 1 > limit:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def _size(blocks: Sequence[Block]) -> int:
    return sum(len(b.text) + 40 for b in blocks)


class StudyService:
    def __init__(self, settings: Settings, metadata: MetadataStore, retriever: Retriever,
                 llm: LLMClient) -> None:
        self.settings = settings
        self.metadata = metadata
        self.retriever = retriever
        self.llm = llm

    # ---- gathering the material ----
    def gather(self, req: StudyRequest) -> Plan:
        if req.task not in TASKS:
            raise StudyError(f"Unknown task: {req.task}")
        documents = self.metadata.list_documents()
        wanted = set(req.document_ids) if req.document_ids else {d.id for d in documents}
        selected = sorted((d for d in documents if d.id in wanted), key=lambda d: d.filename)
        if not selected:
            raise StudyError("Upload a document first.")
        pages = parse_page_ranges(req.pages)

        chunks: list[StoredChunk] = []
        if pages or not req.topic:
            for document in selected:
                chunks += [c for c in self.metadata.get_document_chunks(document.id)
                           if not pages or c.page in pages]
        else:
            found = self.retriever.retrieve(req.topic, top_k=MAX_TOPIC_CHUNKS,
                                            document_ids=[d.id for d in selected])
            order = {d.id: i for i, d in enumerate(selected)}
            chunks = sorted((r.chunk for r in found), key=lambda c: (order[c.doc_id], c.index))
        if not chunks:
            raise StudyError("No text was found for the selected pages or topic.")

        grouped: dict[tuple[str, int], list[StoredChunk]] = {}
        for chunk in chunks:
            grouped.setdefault((chunk.doc_id, chunk.page), []).append(chunk)
        # Word, text and similar files are all "page 1", so big pages are cut into pieces. Small
        # pieces let long documents be read in parts or sampled evenly.
        limit = max(300, min(4000, self.settings.study_context_chars // 4))
        blocks = [Block(doc_id, group[0].filename, page, piece)
                  for (doc_id, page), group in grouped.items()
                  for piece in _split_text(merge_overlapping([c.text for c in group]), limit)]
        names: dict[str, list[int]] = {}
        for block in blocks:
            names.setdefault(block.filename, []).append(block.page)
        sources = [{"filename": name, "pages": sorted(set(p))} for name, p in names.items()]
        return Plan(blocks, sources)

    # ---- fitting long material into the model's reading limit ----
    def _sample(self, blocks: list[Block], budget: int) -> tuple[list[Block], bool]:
        if _size(blocks) <= budget:
            return blocks, False
        average = _size(blocks) / len(blocks)
        keep = max(1, int(budget // average))
        step = len(blocks) / keep
        picked = [blocks[int(i * step)] for i in range(keep)]
        fitted: list[Block] = []
        used = 0
        for block in picked:
            room = budget - used
            if room < 200:
                break
            text = block.text if len(block.text) + 40 <= room else block.text[: room - 40]
            fitted.append(Block(block.doc_id, block.filename, block.page, text))
            used += len(text) + 40
        return fitted, True

    def _groups(self, blocks: list[Block], budget: int) -> tuple[list[list[Block]], bool]:
        groups: list[list[Block]] = []
        current: list[Block] = []
        used = 0
        for block in blocks:
            size = len(block.text) + 40
            if current and used + size > budget:
                groups.append(current)
                current, used = [], 0
            current.append(block)
            used += size
        if current:
            groups.append(current)
        limit = self.settings.study_max_parts
        if len(groups) <= limit:
            return groups, False
        step = len(groups) / limit
        return [groups[int(i * step)] for i in range(limit)], True

    # ---- running ----
    def run(self, req: StudyRequest) -> Iterator[dict]:
        """Events: meta, status (many), token (many), final."""
        language = req.language if req.language in LANGUAGE_NAMES else "en"
        plan = self.gather(req)
        yield {"type": "meta", "sources": plan.sources, "pages": len(plan.blocks)}

        if not self.llm.is_real_model:
            markdown = study_offline.generate(
                req.task, plan.blocks, language=language, topic=req.topic, length=req.length,
                count=req.count, total_marks=req.total_marks)
            yield {"type": "token", "text": markdown}
            yield self._final(markdown, req, language, sampled=False, offline=True)
            return

        budget = self.settings.study_context_chars
        sampled = False
        note = ""
        system = system_prompt(language)
        if req.task in ("summary", "notes") and _size(plan.blocks) > budget:
            groups, sampled = self._groups(plan.blocks, budget)
            partials: list[str] = []
            for number, group in enumerate(groups, start=1):
                yield {"type": "status", "step": number, "total": len(groups)}
                partials.append(self.llm.generate(
                    system,
                    f"Study material (part {number} of {len(groups)}):\n{_format(group)}\n\n"
                    "Task: Write faithful, detailed revision notes for this part only. Keep every "
                    "key term, definition, number, list, formula and the (p. N) page references. "
                    "Use Markdown bullets.", temperature=0.2))
            material = "\n\n".join(f"### Part {i}\n{text}" for i, text in enumerate(partials, 1))
            note = ("\n\n(The material above is a set of notes made from a long document, "
                    "read in order.)")
        else:
            blocks, sampled = self._sample(plan.blocks, budget)
            material = _format(blocks)
            if sampled:
                note = "\n\n(The document is long, so pages spread across it are shown.)"

        pieces: list[str] = []
        for piece in self.llm.stream(system, user_prompt(req, material, note), temperature=0.3):
            pieces.append(piece)
            yield {"type": "token", "text": piece}
        markdown = "".join(pieces).strip()
        yield self._final(markdown, req, language, sampled=sampled, offline=False)

    def _final(self, markdown: str, req: StudyRequest, language: str, *, sampled: bool,
               offline: bool) -> dict:
        return {"type": "final", "markdown": markdown, "task": req.task, "language": language,
                "model": self.llm.name, "sampled": sampled, "offline": offline}

    def run_all(self, req: StudyRequest) -> dict:
        """Run to the end and return the final event (used by the non streaming endpoint)."""
        final: Optional[dict] = None
        meta: dict = {}
        for event in self.run(req):
            if event["type"] == "meta":
                meta = event
            elif event["type"] == "final":
                final = event
        assert final is not None
        final["sources"] = meta.get("sources", [])
        return final
