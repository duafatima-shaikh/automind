"""Small text helpers shared by keyword search, reranking, citation checks and study tools.

Works for English and for Arabic-script languages (Urdu, Sindhi).
"""
from __future__ import annotations

import re

# Letters and digits in any script. Underscore is not a word character for us.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?۔؟])\s+|\n{2,}")
_ARABIC_SCRIPT = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")

# Marks and variants that differ between writers and keyboards but mean the same thing.
_DIACRITICS = re.compile(r"[ً-ٰٟـۖ-ۭ]")
_ARABIC_MAP = str.maketrans({
    "ي": "ی", "ى": "ی", "ې": "ی", "ے": "ی",  # yeh forms
    "ك": "ک", "ڪ": "ک",                                        # kaf forms
    "ه": "ہ", "ھ": "ہ", "ۃ": "ہ", "ە": "ہ",  # heh forms
    "أ": "ا", "إ": "ا", "آ": "ا",                    # alef forms
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    "۰": "0", "۱": "1", "۲": "2", "۳": "3", "۴": "4",
    "۵": "5", "۶": "6", "۷": "7", "۸": "8", "۹": "9",
})


def has_arabic_script(text: str) -> bool:
    return bool(_ARABIC_SCRIPT.search(text))


def arabic_script_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if _ARABIC_SCRIPT.match(c)) / len(letters)


def normalize(text: str) -> str:
    """Lower case, and unify the spelling variants of Arabic-script letters."""
    text = text.lower()
    if has_arabic_script(text):
        text = _DIACRITICS.sub("", text).translate(_ARABIC_MAP)
    return text


_ENGLISH_STOPWORDS = """a an the and or but if of to in on at by for with from as is are was were be
    been being it its this that these those what which who whom whose when where why how do does did
    can could should would will shall may might must not no yes than then so such into about over
    under between during after before up down out off he she they we you i his her their our your
    my me him them us there here also very more some any each other much many"""

# Common function words of Urdu and Sindhi (written in their usual spelling, then normalized).
_URDU_STOPWORDS = """کا کی کے کو سے میں پر اور ہے ہیں تھا تھی تھے ہو ہوتا ہوتی ہوتے یہ وہ جو کہ نے
    بھی کیا کیسے کیوں کون کب کہاں کس کوئی ایک اس ان کر کرنا کرتے کرتی ہم آپ تم لیے لئے ساتھ
    بعد پہلے ہوا ہوئی ہوئے گیا گئی گئے والا والی والے سب کچھ اپنا اپنی اپنے"""
_SINDHI_STOPWORDS = """جو جي جا جون ۾ تي کي کان ۽ آهي آهن هو هيو هئا هي هيءَ ته ڇا ڪيئن ڇو ڪير
    ڪڏهن ڪٿي هڪ ان انهن اهو اها اهي پڻ به سان لاءِ لاء کانپوءِ پهريان ٿيو ٿي ٿيا ٿئي سڀ ڪجهه
    پنهنجو پنهنجي پنهنجا"""

STOPWORDS = frozenset(_ENGLISH_STOPWORDS.split()) | frozenset(
    normalize(word) for word in (_URDU_STOPWORDS + " " + _SINDHI_STOPWORDS).split()
)


def stem(token: str) -> str:
    """A very light English stemmer so 'devices' matches 'device' and 'brewing' matches 'brew'.
    Words in other scripts are left alone."""
    if not token.isascii():
        return token
    if len(token) > 4 and token.endswith("ies"):
        token = token[:-3] + "y"
    elif token.endswith(("sses", "ches", "shes", "xes")):
        token = token[:-2]
    elif len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        token = token[:-1]
    if len(token) > 5 and token.endswith("ing"):
        token = token[:-3]
    elif len(token) > 4 and token.endswith("ed"):
        token = token[:-2]
    return token


def tokenize(text: str, *, remove_stopwords: bool = True, do_stem: bool = True) -> list[str]:
    tokens = _TOKEN.findall(normalize(text))
    if remove_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    if do_stem:
        tokens = [stem(t) for t in tokens]
    return tokens


def content_terms(text: str) -> list[str]:
    return tokenize(text)


def term_coverage(query: str, text: str) -> float:
    """Share of the question's meaningful words that also appear in the text (0 to 1)."""
    query_terms = set(content_terms(query))
    if not query_terms:
        return 0.0
    text_terms = set(content_terms(text))
    return len(query_terms & text_terms) / len(query_terms)


def split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_SPLIT.split(text)
    return [re.sub(r"\s+", " ", p).strip() for p in parts if p and p.strip()]


def merge_overlapping(texts: list[str]) -> str:
    """Join consecutive chunk texts, dropping the sentences that overlap with the previous one."""
    merged: list[str] = []
    for text in texts:
        sentences = split_sentences(text)
        if merged:
            limit = min(len(merged), len(sentences))
            for size in range(limit, 0, -1):
                if merged[-size:] == sentences[:size]:
                    sentences = sentences[size:]
                    break
        merged.extend(sentences)
    return " ".join(merged)


def parse_page_ranges(spec: str | None, limit: int = 5000) -> set[int]:
    """'3-5, 8' -> {3, 4, 5, 8}. Anything that is not a number or range is ignored."""
    pages: set[int] = set()
    if not spec:
        return pages
    for part in re.split(r"[,\s;]+", spec.translate(_ARABIC_MAP)):
        match = re.fullmatch(r"(\d+)(?:[-–](\d+))?", part)
        if not match:
            continue
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if end < start:
            start, end = end, start
        pages.update(range(start, min(end, start + limit) + 1))
    return pages
