"""Versioned prompt templates. Change PROMPT_VERSION whenever the wording changes,
so evaluation results can be traced to the exact prompt that produced them."""
from __future__ import annotations

from typing import Optional, Sequence

PROMPT_VERSION = "v2"

NOT_FOUND_MESSAGE = "I could not find the answer in the uploaded documents."

LANGUAGE_NAMES = {
    "en": "English",
    "ur": "Urdu (اردو), written in Urdu script",
    "sd": "Sindhi (سنڌي), written in Sindhi Arabic script (not Urdu, not Devanagari)",
}

SYSTEM_PROMPT = f"""You answer questions using only the numbered sources provided.
Rules:
1. Use only facts that appear in the sources. Never use outside knowledge.
2. After every sentence that states a fact, add the number of the source in square brackets, like [1] or [1][2].
3. If the sources do not contain the answer, reply with exactly: {NOT_FOUND_MESSAGE}
4. Keep the answer short, clear and in plain language."""


def language_instruction(language: Optional[str]) -> str:
    """Extra system prompt text that fixes the answer language. Empty for English."""
    if not language or language == "en" or language not in LANGUAGE_NAMES:
        return ""
    return (
        f"\n5. Write the whole answer in {LANGUAGE_NAMES[language]}, even if the sources are in "
        "another language. Keep the citation numbers as digits in square brackets. Keep names, "
        "numbers, formulas and code unchanged. If the sources do not contain the answer, still "
        f"reply with exactly: {NOT_FOUND_MESSAGE}"
    )


def system_prompt(language: Optional[str] = "en") -> str:
    return SYSTEM_PROMPT + language_instruction(language)


def build_user_prompt(question: str, sources: Sequence["SourceLike"],
                      history: Sequence[tuple[str, str]] = ()) -> str:
    blocks = []
    for source in sources:
        blocks.append(f"[{source.number}] (file: {source.filename}, page: {source.page})\n{source.text}")
    joined = "\n\n".join(blocks)
    previous = ""
    if history:
        lines = [f"Question: {q}\nAnswer: {a[:300]}" for q, a in history[-3:]]
        previous = "Earlier in this conversation (for context only):\n" + "\n".join(lines) + "\n\n"
    return f"Sources:\n{joined}\n\n{previous}Question: {question}\n\nAnswer:"


class SourceLike:  # documentation only: anything with number, filename, page, text
    number: int
    filename: str
    page: int
    text: str
