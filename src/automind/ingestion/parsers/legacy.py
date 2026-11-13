"""Old Microsoft formats (doc, ppt, xls) are converted with LibreOffice when it is installed."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from . import LEGACY_OFFICE, UnsupportedFileType


def _soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def convert_with_libreoffice(content: bytes, extension: str, target: str) -> bytes:
    program = _soffice()
    if program is None:
        raise UnsupportedFileType(
            f"Files of type '{extension}' are old Microsoft formats. Install LibreOffice so they "
            f"can be converted, or save the file as .{target} and upload that."
        )
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / f"input{extension}"
        source.write_bytes(content)
        try:
            subprocess.run(
                [program, "--headless", "--convert-to", target, "--outdir", folder, str(source)],
                check=True, capture_output=True, timeout=180,
            )
        except (subprocess.SubprocessError, OSError) as error:
            raise UnsupportedFileType(f"LibreOffice could not convert this file: {error}") from error
        output = Path(folder) / f"input.{target}"
        if not output.exists():
            raise UnsupportedFileType("LibreOffice could not convert this file")
        return output.read_bytes()


def make_legacy_parser(extension: str):
    target = LEGACY_OFFICE[extension]

    def parse(content: bytes, settings=None):
        converted = convert_with_libreoffice(content, extension, target)
        if target == "docx":
            from .docx import parse_docx as inner
        elif target == "pptx":
            from .pptx import parse_pptx as inner
        else:
            from .xlsx import parse_xlsx as inner
        return inner(converted, settings)

    return parse
