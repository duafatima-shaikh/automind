from __future__ import annotations

from html.parser import HTMLParser

from . import Page

_SKIP = {"script", "style", "noscript", "head"}
_BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):  # noqa: ANN001
        if tag in _SKIP:
            self._skip_depth += 1
        elif tag in _BLOCK:
            self.parts.append("\n\n" if tag != "br" else "\n")

    def handle_endtag(self, tag):  # noqa: ANN001
        if tag in _SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK:
            self.parts.append("\n\n")

    def handle_data(self, data):  # noqa: ANN001
        if not self._skip_depth:
            self.parts.append(data)


def parse_html(content: bytes, settings=None) -> list[Page]:
    extractor = _TextExtractor()
    extractor.feed(content.decode("utf-8", errors="replace"))
    return [Page(1, "".join(extractor.parts))]
