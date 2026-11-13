from __future__ import annotations

import io

from . import Page


def parse_docx(content: bytes, settings=None) -> list[Page]:
    from docx import Document
    from docx.table import Table

    document = Document(io.BytesIO(content))
    lines: list[str] = []
    for block in document.iter_inner_content():  # keeps paragraphs and tables in order
        if isinstance(block, Table):
            for row in block.rows:
                cells = []
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and (not cells or cells[-1] != text):  # merged cells repeat
                        cells.append(text)
                if cells:
                    lines.append(" | ".join(cells))
        elif block.text.strip():
            lines.append(block.text.strip())
    # Word files do not store page numbers, so everything is treated as page 1.
    return [Page(1, "\n\n".join(lines))]
