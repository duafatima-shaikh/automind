"""Turn spreadsheet rows into sentences that keep the column names.

A bare row such as "Chair | 49 | 12" says nothing on its own. Written as
"Sales, row 3: Product: Chair | Price: 49 | Stock: 12" it can be searched and cited.
"""
from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable, Optional


def format_value(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:g}" if abs(value) < 1e15 else str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def rows_to_lines(label: str, rows: Iterable[tuple], max_rows: int) -> list[str]:
    lines: list[str] = []
    header: Optional[list[Optional[str]]] = None
    count = 0
    for number, row in enumerate(rows, start=1):
        cells = [format_value(v) for v in row]
        if not any(cells):
            continue
        if header is None and count == 0:
            filled = [c for c in cells if c]
            if len(filled) >= 2 and all(isinstance(v, str) for v in row if v is not None):
                header = cells
                lines.append(f"{label}, columns: " + ", ".join(c for c in cells if c))
                count += 1
                continue
            header = []
        count += 1
        if count > max_rows:
            lines.append(f"{label}: more rows were skipped (limit {max_rows}).")
            break
        parts = []
        for index, cell in enumerate(cells):
            if not cell:
                continue
            name = header[index] if header and index < len(header) and header[index] else None
            parts.append(f"{name}: {cell}" if name else cell)
        lines.append(f"{label}, row {number}: " + " | ".join(parts))
    return lines
