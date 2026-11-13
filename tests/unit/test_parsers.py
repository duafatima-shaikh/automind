import io

import pytest
from docx import Document

from automind.ingestion.parsers import EmptyDocumentError, UnsupportedFileType, parse_document
from tests.fixtures.make_pdf import make_pdf


def test_text_and_markdown():
    assert parse_document("a.txt", b"Hello world")[0].text == "Hello world"
    assert "Title" in parse_document("a.md", b"# Title\n\nBody")[0].text


def test_html_skips_scripts():
    page = parse_document("a.html", b"<html><script>bad()</script><p>Good text</p></html>")[0]
    assert "Good text" in page.text and "bad()" not in page.text


def test_docx_reads_paragraphs_and_tables():
    document = Document()
    document.add_paragraph("A paragraph about coffee.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Ratio"
    table.rows[0].cells[1].text = "1 to 16"
    buffer = io.BytesIO()
    document.save(buffer)
    text = parse_document("a.docx", buffer.getvalue())[0].text
    assert "coffee" in text and "Ratio | 1 to 16" in text


def test_pdf_pages_are_numbered():
    pages = parse_document("a.pdf", make_pdf(["First page text", "Second page text"]))
    assert [p.number for p in pages] == [1, 2]
    assert "Second page" in pages[1].text


def test_unsupported_and_empty():
    with pytest.raises(UnsupportedFileType):
        parse_document("a.exe", b"MZ\x90\x00" + bytes(range(256)))
    with pytest.raises(EmptyDocumentError):
        parse_document("a.txt", b"   \n  ")
