from automind.ingestion.chunker import chunk_pages
from automind.ingestion.parsers import Page
from automind.store.bm25_store import BM25Store
from automind.utils.text import (merge_overlapping, normalize, parse_page_ranges, split_sentences,
                                 term_coverage, tokenize)

URDU = "پاکستان کا دارالحکومت اسلام آباد ہے۔ کراچی سب سے بڑا شہر ہے۔ لاہور پنجاب کا مرکز ہے۔"
SINDHI = "سنڌ جو گاديءَ جو شهر ڪراچي آهي. حيدرآباد سنڌ جو ٻيو وڏو شهر آهي."


def test_urdu_words_are_tokenized_and_stopwords_removed():
    tokens = tokenize("پاکستان کا دارالحکومت اسلام آباد ہے")
    assert "پاکستان" in tokens and "دارالحکومت" in tokens
    assert "کا" not in tokens and "ہے" not in tokens


def test_sindhi_words_are_tokenized_and_stopwords_removed():
    tokens = tokenize("سنڌ جو گاديءَ جو شهر ڪراچي آهي")
    assert tokens and "جو" not in tokens and "آهي" not in tokens


def test_spelling_variants_match():
    # Arabic yeh/kaf/heh and Persian/Arabic digits are unified
    assert normalize("كتاب") == normalize("کتاب")
    assert normalize("١٢٣") == "123"
    assert term_coverage("کتاب", "یہ کتاب اچھی ہے") == 1.0


def test_english_tokenizing_is_unchanged():
    assert tokenize("The devices brewing coffee") == ["device", "brew", "coffee"]
    assert tokenize("Brewing devices") == ["brew", "device"]


def test_urdu_sentences_split_on_full_stop_and_question_mark():
    parts = split_sentences("یہ پہلا جملہ ہے۔ کیا یہ دوسرا ہے؟ ہاں یہ تیسرا ہے۔")
    assert len(parts) == 3


def test_urdu_and_sindhi_text_can_be_searched():
    store = BM25Store()
    store.add("u", "d1", URDU)
    store.add("s", "d2", SINDHI)
    store.add("e", "d3", "Coffee is brewed with hot water.")
    assert store.search("پاکستان کا دارالحکومت", 3)[0][0] == "u"
    assert store.search("ڪراچي", 3)[0][0] == "s"


def test_chunker_keeps_urdu_sentences_whole():
    chunks = chunk_pages("d", [Page(1, URDU * 6)], 120, 30)
    assert len(chunks) > 1
    assert all(c.text.rstrip().endswith("۔") for c in chunks)


def test_merge_overlapping_removes_repeated_sentences():
    first = "One is here. Two is here. Three is here."
    second = "Two is here. Three is here. Four is here."
    assert merge_overlapping([first, second]) == \
        "One is here. Two is here. Three is here. Four is here."


def test_page_ranges():
    assert parse_page_ranges("3-5, 8") == {3, 4, 5, 8}
    assert parse_page_ranges("٢-٣") == {2, 3}
    assert parse_page_ranges("abc") == set()
    assert parse_page_ranges(None) == set()
