from __future__ import annotations

import io

from . import Page
from .tables import rows_to_lines


def parse_xlsx(content: bytes, settings=None) -> list[Page]:
    from openpyxl import load_workbook

    limit = settings.max_table_rows if settings else 20000
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    pages = []
    try:
        for number, sheet in enumerate(workbook.worksheets, start=1):
            lines = rows_to_lines(f"Sheet {sheet.title}", sheet.iter_rows(values_only=True), limit)
            # One sheet is one page, so citations show the sheet number.
            pages.append(Page(number, "\n\n".join(lines)))
    finally:
        workbook.close()
    return pages
