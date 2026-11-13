import io

from docx import Document

from automind.utils.docx_export import markdown_to_docx

MARKDOWN = """# Mid-term exam

**Time allowed:** 60 minutes

## Section A

1. Pick the right word: _____
   - A) one
   - B) two

- a bullet with **bold** and *italic*
> a quote

---ANSWERS---

1. **A**
"""


def open_docx(data: bytes) -> Document:
    return Document(io.BytesIO(data))


def test_headings_lists_and_bold_are_written():
    document = open_docx(markdown_to_docx(MARKDOWN, title="Exam"))
    texts = [p.text for p in document.paragraphs]
    assert "Exam" in texts and "Section A" in texts
    assert any(p.style.name.startswith("List Bullet") and "bold" in p.text for p in document.paragraphs)
    bold = [r.text for p in document.paragraphs for r in p.runs if r.bold]
    assert "Time allowed:" in bold and "bold" in bold


def test_answer_marker_becomes_a_page_break_and_is_not_printed():
    document = open_docx(markdown_to_docx(MARKDOWN))
    assert not any("---ANSWERS---" in p.text for p in document.paragraphs)
    assert 'w:br w:type="page"' in document.element.xml or "w:type=\"page\"" in document.element.xml


def test_urdu_paragraphs_are_right_to_left():
    document = open_docx(markdown_to_docx("## خلاصہ\n\nیہ ایک جملہ ہے۔", rtl=True))
    assert document.element.xml.count("<w:bidi/>") >= 2
