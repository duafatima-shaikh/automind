"""Turn the Markdown produced by the study tools into a Word (.docx) file.

Handles headings, bullet and numbered lines, bold and italic text, quotes and page breaks, and
writes right to left paragraphs for Urdu and Sindhi.
"""
from __future__ import annotations

import io
import re

from docx import Document
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

_INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\n]+\*)")
_NUMBERED = re.compile(r"^(\d+)[.)]\s+(.*)$")
_BULLET = re.compile(r"^(\s*)[-*•]\s+(.*)$")
_OPTION = re.compile(r"^[A-Da-d]\)\s")
_MARKER = "---ANSWERS---"


def _rtl_paragraph(paragraph) -> None:
    properties = paragraph._p.get_or_add_pPr()
    properties.append(OxmlElement("w:bidi"))


def _rtl_run(run) -> None:
    properties = run._r.get_or_add_rPr()
    properties.append(OxmlElement("w:rtl"))
    fonts = properties.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        properties.insert(0, fonts)
    fonts.set(qn("w:cs"), "Arial")


def _add_runs(paragraph, text: str, rtl: bool, bold: bool = False) -> None:
    for part in _INLINE.split(text):
        if not part:
            continue
        strong = part.startswith("**") and part.endswith("**") and len(part) > 4
        slanted = not strong and part.startswith("*") and part.endswith("*") and len(part) > 2
        content = part[2:-2] if strong else (part[1:-1] if slanted else part)
        run = paragraph.add_run(content)
        run.bold = bold or strong
        run.italic = slanted
        if rtl:
            _rtl_run(run)


def markdown_to_docx(markdown: str, title: str = "", rtl: bool = False) -> bytes:
    document = Document()
    section = document.sections[0]
    section.left_margin = section.right_margin = Inches(1)
    base = document.styles["Normal"]
    base.font.name = "Calibri"
    base.font.size = Pt(11)

    if title:
        heading = document.add_heading(title, level=0)
        if rtl:
            _rtl_paragraph(heading)
            for run in heading.runs:
                _rtl_run(run)

    for raw in markdown.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == _MARKER:
            document.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            continue

        heading = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if heading:
            paragraph = document.add_heading(level=min(len(heading.group(1)), 3))
            _add_runs(paragraph, heading.group(2), rtl)
        elif stripped.startswith(">"):
            paragraph = document.add_paragraph()
            paragraph.paragraph_format.left_indent = Inches(0.3)
            _add_runs(paragraph, stripped.lstrip("> ").strip(), rtl)
            for run in paragraph.runs:
                run.italic = True
                run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        else:
            bullet = _BULLET.match(line)
            numbered = _NUMBERED.match(stripped)
            if bullet and _OPTION.match(bullet.group(2)):
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Inches(0.6)
                paragraph.paragraph_format.space_after = Pt(0)
                _add_runs(paragraph, bullet.group(2), rtl)
            elif bullet:
                indent = len(bullet.group(1)) >= 2
                paragraph = document.add_paragraph(style="List Bullet 2" if indent else "List Bullet")
                _add_runs(paragraph, bullet.group(2), rtl)
            elif numbered:
                paragraph = document.add_paragraph()
                paragraph.paragraph_format.left_indent = Inches(0.3)
                paragraph.paragraph_format.first_line_indent = Inches(-0.3)
                paragraph.paragraph_format.space_after = Pt(2)
                _add_runs(paragraph, f"{numbered.group(1)}. {numbered.group(2)}", rtl)
            else:
                paragraph = document.add_paragraph()
                _add_runs(paragraph, stripped, rtl)
        if rtl:
            _rtl_paragraph(paragraph)

    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
