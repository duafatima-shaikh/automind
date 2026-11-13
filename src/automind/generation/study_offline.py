"""Basic study tools that need no language model.

They pick the most important sentences of the material and rearrange them into summaries, notes,
quizzes, flashcards, assignments and exams. The questions are simple (fill in the blank, define,
discuss) and every sentence comes straight from the document, so nothing is invented. Connect a
language model for natural wording, translation and better questions.
"""
from __future__ import annotations

import math
import random
import re
import zlib
from collections import Counter
from dataclasses import dataclass
from typing import Optional, Sequence

from ..utils.text import split_sentences, term_coverage, tokenize

ANSWER_MARKER = "---ANSWERS---"

LABELS: dict[str, dict[str, str]] = {
    "en": {
        "basic": "Basic mode: this was made without an AI model, so it only rearranges sentences "
                 "from your document. Connect an AI model in Settings for natural questions, "
                 "better notes and Urdu or Sindhi output.",
        "summary": "Summary", "key_points": "Key points", "notes": "Study notes",
        "key_terms": "Key terms", "page": "p.", "explain": "Explanation",
        "related": "Most relevant passages", "not_found": "Nothing about this topic was found "
        "in the selected material.", "quiz": "Quiz", "flashcards": "Flashcards",
        "assignment": "Assignment", "mid_exam": "Mid-term exam", "final_exam": "Final exam",
        "time": "Time allowed", "minutes": "minutes", "total": "Total marks", "marks": "marks",
        "section": "Section", "mcq": "Multiple choice questions", "short": "Short questions",
        "long": "Long questions", "fill": "Choose the word that best completes the statement.",
        "define": "Define {t} and explain it in your own words.",
        "discuss": "Discuss {a} and {b} in detail with reference to the material.",
        "answer_key": "Answer key", "guide": "Marking guide", "q": "Q", "a": "A",
        "attempt_all": "Attempt all questions.", "part": "Part",
        "card_q": "What does the material say about {t}?",
    },
    "ur": {
        "basic": "بنیادی موڈ: یہ مواد بغیر اے آئی ماڈل کے تیار ہوا ہے، اس لیے صرف آپ کی دستاویز کے "
                 "جملے ترتیب دیے گئے ہیں۔ بہتر سوالات، نوٹس اور اردو یا سندھی آؤٹ پٹ کے لیے سیٹنگز میں "
                 "اے آئی ماڈل جوڑیں۔",
        "summary": "خلاصہ", "key_points": "اہم نکات", "notes": "مطالعاتی نوٹس",
        "key_terms": "اہم اصطلاحات", "page": "ص", "explain": "وضاحت",
        "related": "متعلقہ اقتباسات", "not_found": "منتخب مواد میں اس موضوع کے بارے میں کچھ "
        "نہیں ملا۔", "quiz": "کوئز", "flashcards": "فلیش کارڈز", "assignment": "اسائنمنٹ",
        "mid_exam": "مڈ ٹرم امتحان", "final_exam": "فائنل امتحان", "time": "دورانیہ",
        "minutes": "منٹ", "total": "کل نمبر", "marks": "نمبر", "section": "حصہ",
        "mcq": "کثیر انتخابی سوالات", "short": "مختصر سوالات", "long": "تفصیلی سوالات",
        "fill": "وہ درست لفظ منتخب کریں جو جملہ مکمل کرے۔",
        "define": "{t} کی تعریف کریں اور اپنے الفاظ میں وضاحت کریں۔",
        "discuss": "مواد کے حوالے سے {a} اور {b} پر تفصیلی بحث کریں۔",
        "answer_key": "جوابات", "guide": "مارکنگ گائیڈ", "q": "سوال", "a": "جواب",
        "attempt_all": "تمام سوالات حل کریں۔", "part": "حصہ",
        "card_q": "مواد میں {t} کے بارے میں کیا بتایا گیا ہے؟",
    },
    "sd": {
        "basic": "بنيادي موڊ: هي مواد AI ماڊل کانسواءِ ٺهيو آهي، تنهنڪري رڳو توهان جي دستاويز جا "
                 "جملا ترتيب ڏنا ويا آهن. بهتر سوالن، نوٽس ۽ سنڌي يا اردو آئوٽ پُٽ لاءِ سيٽنگز ۾ "
                 "AI ماڊل ڳنڍيو.",
        "summary": "خلاصو", "key_points": "اهم نڪتا", "notes": "مطالعاتي نوٽس",
        "key_terms": "اهم اصطلاح", "page": "ص", "explain": "وضاحت",
        "related": "لاڳاپيل اقتباس", "not_found": "چونڊيل مواد ۾ هن موضوع بابت ڪجهه نه مليو.",
        "quiz": "ڪوئز", "flashcards": "فليش ڪارڊ", "assignment": "اسائنمينٽ",
        "mid_exam": "مڊ ٽرم امتحان", "final_exam": "فائنل امتحان", "time": "وقت",
        "minutes": "منٽ", "total": "ڪل نمبر", "marks": "نمبر", "section": "حصو",
        "mcq": "گھڻن چونڊن وارا سوال", "short": "مختصر سوال", "long": "تفصيلي سوال",
        "fill": "صحيح لفظ چونڊيو جيڪو جملو مڪمل ڪري.",
        "define": "{t} جي وصف ڏيو ۽ پنهنجن لفظن ۾ وضاحت ڪريو.",
        "discuss": "مواد جي حوالي سان {a} ۽ {b} تي تفصيلي بحث ڪريو.",
        "answer_key": "جواب", "guide": "مارڪنگ گائيڊ", "q": "سوال", "a": "جواب",
        "attempt_all": "سڀ سوال حل ڪريو.", "part": "حصو",
        "card_q": "مواد ۾ {t} بابت ڇا چيو ويو آهي؟",
    },
}

# Common words that make poor key terms or quiz answers.
_WEAK = frozenset("""most every often called time common first second third other another between among
    about keep even just still well only both either make made makes use used using many much more
    less same such part parts way ways one two three four five six seven eight nine ten each own
    however while without within across around because since until often usually sometimes
    always never every something anything everything people thing things""".split())

_WORD = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_][^\W_]*", re.UNICODE)
_LETTERS = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


@dataclass
class Sentence:
    text: str
    page: int
    filename: str
    order: int
    terms: frozenset
    score: float = 0.0


class Material:
    """The material split into scored sentences."""

    def __init__(self, blocks: Sequence) -> None:
        self.sentences: list[Sentence] = []
        for block in blocks:
            for text in split_sentences(block.text):
                words = len(text.split())
                if words < 6 or len(text) > 450:
                    continue
                terms = frozenset(tokenize(text))
                if terms:
                    self.sentences.append(
                        Sentence(text, block.page, block.filename, len(self.sentences), terms))
        self.tf: Counter = Counter()
        for sentence in self.sentences:
            self.tf.update(sentence.terms)
        self.surface = self._surface_forms()
        pages = max(1, len({(s.filename, s.page) for s in self.sentences}))
        for sentence in self.sentences:
            useful = [self.tf[t] for t in sentence.terms]
            sentence.score = sum(min(v, 8) for v in useful) / (len(useful) ** 0.7)
        self.n_pages = pages

    def _surface_forms(self) -> dict[str, str]:
        counts: dict[str, Counter] = {}
        for sentence in self.sentences:
            for word in _WORD.findall(sentence.text):
                key = tokenize(word)
                if key:
                    counts.setdefault(key[0], Counter())[word] += 1
        return {term: forms.most_common(1)[0][0] for term, forms in counts.items()}

    def is_good_term(self, term: str) -> bool:
        word = self.surface.get(term, "")
        return (len(word) >= 5 and bool(_LETTERS.fullmatch(word))
                and word.lower() not in _WEAK and term not in _WEAK)

    def key_terms(self, n: int) -> list[str]:
        """Most frequent meaningful words (as written in the document)."""
        ranked = sorted(
            (t for t in self.tf if self.is_good_term(t)),
            key=lambda t: (-self.tf[t], t),
        )
        return [self.surface[t] for t in ranked[:n]]

    def best_sentence(self, term: str) -> Optional[Sentence]:
        keys = tokenize(term)
        if not keys:
            return None
        matching = [s for s in self.sentences if keys[0] in s.terms]
        return max(matching, key=lambda s: s.score) if matching else None

    def top(self, n: int, pool: Optional[Sequence[Sentence]] = None) -> list[Sentence]:
        """The n best sentences, spread over the pages, returned in reading order."""
        pool = list(pool if pool is not None else self.sentences)
        per_page = max(2, math.ceil(n * 1.5 / max(1, self.n_pages)))
        taken: Counter = Counter()
        chosen: list[Sentence] = []
        for sentence in sorted(pool, key=lambda s: -s.score):
            key = (sentence.filename, sentence.page)
            if taken[key] >= per_page:
                continue
            taken[key] += 1
            chosen.append(sentence)
            if len(chosen) == n:
                break
        return sorted(chosen, key=lambda s: s.order)


def _join(labels: dict, items: Sequence[str]) -> str:
    """Join a list with the right separator (Arabic comma for Urdu and Sindhi)."""
    return ("، " if labels["page"] == "ص" else ", ").join(items)


def _ref(labels: dict, sentence: Sentence) -> str:
    return f"({labels['page']} {sentence.page})"


# ---------------------------------------------------------------- multiple choice questions
def _numeric_options(value: int, rng: random.Random) -> list[int]:
    pool = {value + 1, value - 1, value + 2, value * 2, max(value // 2, 0), value + 10,
            max(value - 10, 0)}
    pool.discard(value)
    options = sorted(pool)
    rng.shuffle(options)
    return options[:3]


def _make_mcq(material: Material, sentence: Sentence, used: set[str]) -> Optional[dict]:
    rng = random.Random(zlib.crc32(sentence.text.encode("utf-8")))
    words = _WORD.findall(sentence.text)
    numbers = [w for w in words if w[0].isdigit() and w.isdigit() and len(w) <= 9]
    letters = [w for w in words if tokenize(w) and tokenize(w)[0] not in used
               and material.is_good_term(tokenize(w)[0])]
    if numbers and rng.random() < 0.5:
        answer = numbers[0]
        options = [str(n) for n in _numeric_options(int(answer), rng)]
    elif letters:
        answer = max(letters, key=lambda w: (material.tf[tokenize(w)[0]], len(w)))
        pool = [w for w in material.key_terms(60)
                if w.lower() != answer.lower() and abs(len(w) - len(answer)) <= 4]
        rng.shuffle(pool)
        options = pool[:3]
    else:
        return None
    if len(options) < 3:
        return None
    used.update(tokenize(answer))
    blanked = re.sub(rf"(?<!\w){re.escape(answer)}(?!\w)", "_____", sentence.text, count=1)
    if blanked == sentence.text:
        return None
    choices = options + [answer]
    rng.shuffle(choices)
    return {"text": blanked, "choices": choices, "answer": answer,
            "letter": "ABCD"[choices.index(answer)], "sentence": sentence}


def _mcqs(material: Material, n: int) -> list[dict]:
    used: set[str] = set()
    questions: list[dict] = []
    # Walk the best sentences first, then spread them in reading order.
    for sentence in sorted(material.sentences, key=lambda s: -s.score):
        question = _make_mcq(material, sentence, used)
        if question:
            questions.append(question)
        if len(questions) == n:
            break
    return sorted(questions, key=lambda q: q["sentence"].order)


def _format_mcqs(questions: list[dict], start: int = 1) -> list[str]:
    lines: list[str] = []
    for number, q in enumerate(questions, start=start):
        lines.append(f"{number}. {q['text']}")
        for letter, choice in zip("ABCD", q["choices"]):
            lines.append(f"   - {letter}) {choice}")
        lines.append("")
    return lines


def _mcq_answers(labels: dict, questions: list[dict], start: int = 1) -> list[str]:
    return [f"{number}. **{q['letter']}** — {q['answer']} {_ref(labels, q['sentence'])}"
            for number, q in enumerate(questions, start=start)]


# ---------------------------------------------------------------- tasks
def _summary(material: Material, labels: dict, length: str) -> str:
    n = {"short": 4, "medium": 8, "detailed": 15}.get(length, 8)
    lines = [f"## {labels['summary']}", ""]
    lines += [f"- {s.text} {_ref(labels, s)}" for s in material.top(n)]
    terms = material.key_terms(10)
    if terms:
        lines += ["", f"**{labels['key_terms']}:** " + _join(labels, terms)]
    return "\n".join(lines)


def _notes(material: Material, labels: dict, length: str) -> str:
    per_page = {"short": 2, "medium": 3, "detailed": 5}.get(length, 3)
    pages: dict[tuple[str, int], list[Sentence]] = {}
    for sentence in material.sentences:
        pages.setdefault((sentence.filename, sentence.page), []).append(sentence)
    per_page = max(1, min(per_page, 150 // max(1, len(pages))))
    lines = [f"## {labels['notes']}", ""]
    multi_file = len({name for name, _ in pages}) > 1
    for (filename, page), sentences in pages.items():
        heading = f"{filename} — {labels['page']} {page}" if multi_file else f"{labels['page']} {page}"
        picked = sorted(sorted(sentences, key=lambda s: -s.score)[:per_page], key=lambda s: s.order)
        lines += [f"### {heading}", ""] + [f"- {s.text}" for s in picked] + [""]
    terms = material.key_terms(15)
    if terms:
        lines += [f"### {labels['key_terms']}", "", _join(labels, [f"**{t}**" for t in terms])]
    return "\n".join(lines)


def _explain(material: Material, labels: dict, topic: Optional[str]) -> str:
    lines = [f"## {labels['explain']}" + (f": {topic}" if topic else ""), ""]
    if topic:
        scored = [(term_coverage(topic, s.text), s) for s in material.sentences]
        relevant = [s for c, s in scored if c > 0]
        best = sorted(relevant, key=lambda s: (-term_coverage(topic, s.text), -s.score))[:6]
        chosen = sorted(best, key=lambda s: s.order)
        if not chosen:
            return "\n".join(lines + [labels["not_found"]])
    else:
        chosen = material.top(10)
    lines += [f"- {s.text} {_ref(labels, s)}" for s in chosen]
    return "\n".join(lines)


def _flashcards(material: Material, labels: dict, n: int) -> str:
    lines = [f"## {labels['flashcards']}", ""]
    made = 0
    for term in material.key_terms(n * 2):
        sentence = material.best_sentence(term)
        if not sentence:
            continue
        lines += [f"**{labels['q']}:** " + labels["card_q"].format(t=f"**{term}**"),
                  f"**{labels['a']}:** {sentence.text} {_ref(labels, sentence)}", ""]
        made += 1
        if made == n:
            break
    return "\n".join(lines)


def _quiz(material: Material, labels: dict, n: int) -> str:
    questions = _mcqs(material, n)
    lines = [f"## {labels['quiz']}", "", f"*{labels['fill']}*", ""]
    lines += _format_mcqs(questions)
    lines += [ANSWER_MARKER, "", f"### {labels['answer_key']}", ""]
    lines += _mcq_answers(labels, questions)
    return "\n".join(lines)


def _plan(total: int, mcq_share: float, short_share: float) -> tuple[int, int, int, int, int]:
    """Returns (mcq count, short count, short marks each, long count, long marks each)."""
    n_mcq = max(2, round(total * mcq_share))
    short_marks = 2 if total <= 30 else 3
    n_short = max(2, round(total * short_share / short_marks))
    remaining = max(total - n_mcq - n_short * short_marks, 4)
    long_marks = 5 if total <= 30 else (8 if total < 100 else 10)
    n_long = max(1, remaining // long_marks)
    return n_mcq, n_short, short_marks, n_long, remaining // n_long


def _pair_answer(material: Material, labels: dict, first: str, second: str) -> str:
    seen: list[Sentence] = []
    for term in (first, second):
        sentence = material.best_sentence(term)
        if sentence and sentence not in seen:
            seen.append(sentence)
    return " ".join(f"{s.text} {_ref(labels, s)}" for s in seen)


def _paper(material: Material, labels: dict, task: str, total: int) -> str:
    shares = {"mid_exam": (0.20, 0.40), "final_exam": (0.15, 0.35)}
    n_mcq, n_short, short_marks, n_long, long_marks = _plan(total, *shares.get(task, (0.2, 0.4)))
    mcqs = _mcqs(material, n_mcq)
    terms = material.key_terms(n_short + 2 * n_long + 4)
    short_terms = terms[:n_short]
    pairs = [(terms[n_short + 2 * i], terms[n_short + 2 * i + 1]) for i in range(n_long)
             if n_short + 2 * i + 1 < len(terms)]
    mcq_marks = len(mcqs)
    short_total = len(short_terms) * short_marks
    long_total = len(pairs) * long_marks
    grand = mcq_marks + short_total + long_total
    minutes = 60 if total <= 30 else (120 if total <= 60 else 180)

    lines = [f"# {labels[task]}", "",
             f"**{labels['time']}:** {minutes} {labels['minutes']}  ·  **{labels['total']}:** {grand}",
             "", f"*{labels['attempt_all']}*", ""]
    letter = iter("ABC")
    if mcqs:
        lines += [f"## {labels['section']} {next(letter)}: {labels['mcq']} ({mcq_marks} {labels['marks']})",
                  "", f"*{labels['fill']}*", ""] + _format_mcqs(mcqs)
    number = len(mcqs) + 1
    if short_terms:
        lines += [f"## {labels['section']} {next(letter)}: {labels['short']} "
                  f"({short_total} {labels['marks']})", ""]
        for term in short_terms:
            lines.append(f"{number}. {labels['define'].format(t=f'**{term}**')} "
                         f"*[{short_marks} {labels['marks']}]*")
            number += 1
        lines.append("")
    if pairs:
        lines += [f"## {labels['section']} {next(letter)}: {labels['long']} "
                  f"({long_total} {labels['marks']})", ""]
        for first, second in pairs:
            lines.append(f"{number}. {labels['discuss'].format(a=f'**{first}**', b=f'**{second}**')} "
                         f"*[{long_marks} {labels['marks']}]*")
            number += 1
        lines.append("")

    lines += [ANSWER_MARKER, "", f"### {labels['answer_key']}", ""]
    lines += _mcq_answers(labels, mcqs)
    guide: list[str] = []
    number = len(mcqs) + 1
    for term in short_terms:
        sentence = material.best_sentence(term)
        if sentence:
            guide.append(f"{number}. **{term}** — {sentence.text} {_ref(labels, sentence)}")
        number += 1
    for first, second in pairs:
        guide.append(f"{number}. **{first}**, **{second}** — {_pair_answer(material, labels, first, second)}")
        number += 1
    if guide:
        lines += ["", f"### {labels['guide']}", ""] + guide
    return "\n".join(lines)


def _assignment(material: Material, labels: dict, total: int) -> str:
    n_short = max(2, round(total * 0.4 / 2))
    short_marks = 2
    long_total = total - n_short * short_marks
    n_long = 2 if long_total >= 8 else 1
    long_marks = long_total // n_long
    terms = material.key_terms(n_short + 2 * n_long + 2)
    short_terms = terms[:n_short]
    pairs = [(terms[n_short + 2 * i], terms[n_short + 2 * i + 1]) for i in range(n_long)
             if n_short + 2 * i + 1 < len(terms)]
    grand = len(short_terms) * short_marks + len(pairs) * long_marks
    lines = [f"# {labels['assignment']}", "", f"**{labels['total']}:** {grand}", "",
             f"*{labels['attempt_all']}*", ""]
    number = 1
    lines += [f"## {labels['part']} 1: {labels['short']}", ""]
    for term in short_terms:
        lines.append(f"{number}. {labels['define'].format(t=f'**{term}**')} "
                     f"*[{short_marks} {labels['marks']}]*")
        number += 1
    lines += ["", f"## {labels['part']} 2: {labels['long']}", ""]
    for first, second in pairs:
        lines.append(f"{number}. {labels['discuss'].format(a=f'**{first}**', b=f'**{second}**')} "
                     f"*[{long_marks} {labels['marks']}]*")
        number += 1
    lines += ["", ANSWER_MARKER, "", f"### {labels['guide']}", ""]
    number = 1
    for term in short_terms:
        sentence = material.best_sentence(term)
        if sentence:
            lines.append(f"{number}. **{term}** — {sentence.text} {_ref(labels, sentence)}")
        number += 1
    for first, second in pairs:
        lines.append(f"{number}. **{first}**, **{second}** — "
                     + _pair_answer(material, labels, first, second))
        number += 1
    return "\n".join(lines)


def generate(task: str, blocks: Sequence, *, language: str = "en", topic: Optional[str] = None,
             length: str = "medium", count: Optional[int] = None,
             total_marks: Optional[int] = None) -> str:
    """Build the study material as Markdown. `blocks` need .text, .page and .filename."""
    labels = LABELS.get(language, LABELS["en"])
    material = Material(blocks)
    if not material.sentences:
        return f"> {labels['basic']}\n\n{labels['not_found']}"
    if task == "summary":
        body = _summary(material, labels, length)
    elif task == "notes":
        body = _notes(material, labels, length)
    elif task == "explain":
        body = _explain(material, labels, topic)
    elif task == "flashcards":
        body = _flashcards(material, labels, count or 15)
    elif task == "quiz":
        body = _quiz(material, labels, count or 10)
    elif task == "assignment":
        body = _assignment(material, labels, total_marks or 20)
    elif task in ("mid_exam", "final_exam"):
        body = _paper(material, labels, task, total_marks or (30 if task == "mid_exam" else 60))
    else:
        raise ValueError(f"Unknown task: {task}")
    return f"> {labels['basic']}\n\n{body}"
