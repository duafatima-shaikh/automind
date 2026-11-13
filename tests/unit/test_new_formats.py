import io
import shutil
import zipfile

import pytest
from PIL import Image, ImageDraw, ImageFont

from automind.config import Settings
from automind.ingestion.ocr import OCRUnavailable
from automind.ingestion.parsers import UnsupportedFileType, parse_document


def text_image(*lines, size=40):
    image = Image.new("RGB", (950, 100 * len(lines) + 40), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=size)
    for i, line in enumerate(lines):
        draw.text((20, 20 + i * 100), line, fill="black", font=font)
    return image


def png_bytes(image):
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


# ---------- office files ----------
def test_pptx_slides_notes_and_tables():
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Quarterly plan"
    slide.placeholders[1].text = "Launch the new bike lanes in March"
    slide.notes_slide.notes_text_frame.text = "Mention the budget of 2 million"
    second = presentation.slides.add_slide(presentation.slide_layouts[5])
    second.shapes.title.text = "Prices"
    table = second.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    table.cell(0, 0).text, table.cell(0, 1).text = "Pass", "Cost"
    table.cell(1, 0).text, table.cell(1, 1).text = "Monthly", "18 dollars"
    buffer = io.BytesIO()
    presentation.save(buffer)

    pages = parse_document("deck.pptx", buffer.getvalue())
    assert [p.number for p in pages] == [1, 2]
    assert "Quarterly plan" in pages[0].text and "bike lanes" in pages[0].text
    assert "Speaker notes: Mention the budget" in pages[0].text
    assert "Monthly | 18 dollars" in pages[1].text


def test_xlsx_rows_keep_column_names_per_sheet():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Sales"
    sheet.append(["Product", "Price", "Stock"])
    sheet.append(["Chair", 49.5, 12])
    sheet.append(["Desk", 120, 3])
    other = workbook.create_sheet("Staff")
    other.append(["Name", "Role"])
    other.append(["Amina", "Manager"])
    buffer = io.BytesIO()
    workbook.save(buffer)

    pages = parse_document("data.xlsx", buffer.getvalue())
    assert [p.number for p in pages] == [1, 2]
    assert "Sheet Sales, row 2: Product: Chair | Price: 49.5 | Stock: 12" in pages[0].text
    assert "Name: Amina | Role: Manager" in pages[1].text


def test_xlsx_row_limit():
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["A", "B"])
    for i in range(50):
        sheet.append([f"x{i}", i])
    buffer = io.BytesIO()
    workbook.save(buffer)
    text = parse_document("big.xlsx", buffer.getvalue(), Settings(max_table_rows=10))[0].text
    assert "more rows were skipped" in text and "x49" not in text


def test_csv_and_tsv():
    page = parse_document("p.csv", b"Name,City\nAmina,Karachi\nBilal,Sukkur\n")[0]
    assert "row 2: Name: Amina | City: Karachi" in page.text
    page = parse_document("p.tsv", b"Name\tCity\nAmina\tKarachi\n")[0]
    assert "City: Karachi" in page.text


def test_docx_keeps_order_of_text_and_tables():
    from docx import Document

    document = Document()
    document.add_paragraph("Before the table.")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = "Key", "Value"
    document.add_paragraph("After the table.")
    buffer = io.BytesIO()
    document.save(buffer)
    text = parse_document("a.docx", buffer.getvalue())[0].text
    assert text.index("Before") < text.index("Key | Value") < text.index("After")


def test_old_office_formats_explain_how_to_proceed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    for name in ("old.doc", "old.ppt", "old.xls"):
        with pytest.raises(UnsupportedFileType) as error:
            parse_document(name, b"\xd0\xcf\x11\xe0 not really")
        assert "LibreOffice" in str(error.value)


# ---------- other formats ----------
def test_opendocument_text_and_spreadsheet():
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')
    odt = f'<office:document-content {ns}><office:body><office:text><text:h>Title</text:h><text:p>The gate code is <text:span>4711</text:span>.</text:p></office:text></office:body></office:document-content>'
    ods = (f'<office:document-content {ns}><office:body><office:spreadsheet><table:table table:name="Data">'
           '<table:table-row><table:table-cell><text:p>City</text:p></table:table-cell><table:table-cell><text:p>Sukkur</text:p></table:table-cell></table:table-row>'
           '</table:table></office:spreadsheet></office:body></office:document-content>')
    for name, xml in (("a.odt", odt), ("a.ods", ods)):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("content.xml", xml)
        pages = parse_document(name, buffer.getvalue())
        assert pages
    assert "4711" in parse_document("a.odt", _zip({"content.xml": odt}))[0].text
    assert "Sheet Data, row 1: City | Sukkur" in parse_document("a.ods", _zip({"content.xml": ods}))[0].text


def _zip(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_rtf():
    text = parse_document("a.rtf", rb"{\rtf1\ansi Hello {\b bold} world.\par}")[0].text
    assert "Hello" in text and "bold" in text and "world" in text


def test_epub_chapters_in_reading_order():
    files = {
        "META-INF/container.xml": '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>',
        "OEBPS/content.opf": '<package><manifest><item id="b" href="two.xhtml"/><item id="a" href="one.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>',
        "OEBPS/one.xhtml": "<html><body><p>First chapter text.</p></body></html>",
        "OEBPS/two.xhtml": "<html><body><p>Second chapter text.</p></body></html>",
    }
    pages = parse_document("book.epub", _zip(files))
    assert [p.number for p in pages] == [1, 2]
    assert "First chapter" in pages[0].text and "Second chapter" in pages[1].text


def test_code_json_and_unknown_text_files():
    assert "def hello" in parse_document("a.py", b"def hello():\n    return 1\n")[0].text
    assert '"city": "Sukkur"' in parse_document("a.json", b'{"city":"Sukkur"}')[0].text
    assert "plain words here" in parse_document("README", b"plain words here")[0].text
    assert "notes" in parse_document("data.weird", b"my notes about things")[0].text


def test_unknown_binary_is_rejected():
    with pytest.raises(UnsupportedFileType):
        parse_document("blob.bin", bytes(range(256)) * 10)


def test_type_is_detected_from_content_when_extension_is_missing():
    from tests.fixtures.make_pdf import make_pdf

    assert "Hello there" in parse_document("download", make_pdf(["Hello there"]))[0].text


# ---------- images and scans ----------
def test_image_without_recognition_engine_gives_clear_message(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OCRUnavailable("install it")

    monkeypatch.setattr("automind.ingestion.ocr.ocr_image", unavailable)
    with pytest.raises(OCRUnavailable):
        parse_document("a.png", png_bytes(text_image("hello")))


def test_image_description_is_added_when_enabled(monkeypatch):
    monkeypatch.setattr("automind.ingestion.vision.describe_image",
                        lambda content, mime, settings: "A bar chart of sales by year")
    monkeypatch.setattr("automind.ingestion.ocr.ocr_image", lambda image, backend="auto": "")
    settings = Settings(image_descriptions=True, openai_api_key="x")
    page = parse_document("chart.png", png_bytes(Image.new("RGB", (50, 50))), settings)[0]
    assert "A bar chart of sales by year" in page.text


def test_image_text_is_read():
    pytest.importorskip("rapidocr_onnxruntime")
    page = parse_document("note.png", png_bytes(text_image("The monthly pass costs 18 dollars")))[0]
    assert "monthly pass costs 18 dollars" in page.text.lower().replace("\n", " ")


def test_multi_frame_tiff_has_one_page_per_frame():
    pytest.importorskip("rapidocr_onnxruntime")
    first, second = text_image("Alpha station opens early"), text_image("Bravo station opens late")
    buffer = io.BytesIO()
    first.save(buffer, "TIFF", save_all=True, append_images=[second])
    pages = parse_document("scan.tiff", buffer.getvalue())
    assert [p.number for p in pages] == [1, 2]
    assert "alpha" in pages[0].text.lower() and "bravo" in pages[1].text.lower()


def test_scanned_pdf_pages_are_read():
    pytest.importorskip("rapidocr_onnxruntime")
    pytest.importorskip("pypdfium2")
    buffer = io.BytesIO()
    text_image("Helmets are recommended but not required").save(buffer, "PDF")
    pages = parse_document("scan.pdf", buffer.getvalue(), Settings())
    assert "helmets are recommended" in pages[0].text.lower()
