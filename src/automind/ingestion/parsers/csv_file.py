from __future__ import annotations

import csv
import io

from . import Page
from .tables import rows_to_lines
from .text import decode_text


def parse_csv(content: bytes, settings=None) -> list[Page]:
    text = decode_text(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    limit = settings.max_table_rows if settings else 20000
    rows = (tuple(r) for r in csv.reader(io.StringIO(text), dialect))
    return [Page(1, "\n\n".join(rows_to_lines("Table", rows, limit)))]
