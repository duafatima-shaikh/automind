from __future__ import annotations

import io

from . import Page


def _walk(shapes):
    for shape in shapes:
        if shape.shape_type == 6:  # group of shapes
            yield from _walk(shape.shapes)
        else:
            yield shape


def parse_pptx(content: bytes, settings=None) -> list[Page]:
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(content))
    pages = []
    for number, slide in enumerate(presentation.slides, start=1):
        title = slide.shapes.title
        title_text = title.text_frame.text.strip() if title is not None and title.has_text_frame else ""
        parts = [f"Slide {number}: {title_text}" if title_text else f"Slide {number}"]
        for shape in _walk(slide.shapes):
            if title is not None and shape.shape_id == title.shape_id:
                continue
            if shape.has_text_frame and shape.text_frame.text.strip():
                parts.append(shape.text_frame.text.strip())
            elif getattr(shape, "has_table", False) and shape.has_table:
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells if c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                parts.append(f"Speaker notes: {notes}")
        # A slide with only its number has no content.
        pages.append(Page(number, "\n\n".join(parts) if len(parts) > 1 else ""))
    return pages
