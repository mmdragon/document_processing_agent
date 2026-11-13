"""Optional Tesseract OCR, used through PyMuPDF's OCR text pages.

Tesseract is an external program (macOS: ``brew install tesseract``). If it is not
installed, OCR is reported as unavailable and pages without a text layer are marked
``needs_ocr`` instead of failing.
"""

from __future__ import annotations

import shutil
from typing import Protocol

import pymupdf


class OcrEngine(Protocol):
    name: str

    def page_words(self, page: pymupdf.Page) -> list[tuple]:
        """Return PyMuPDF-style word tuples (x0, y0, x1, y1, word, ...)."""
        ...


class TesseractOcr:
    name = "tesseract"

    def __init__(self, language: str = "eng", dpi: int = 300) -> None:
        self.language = language
        self.dpi = dpi

    @staticmethod
    def is_installed() -> bool:
        return shutil.which("tesseract") is not None

    def page_words(self, page: pymupdf.Page) -> list[tuple]:
        textpage = page.get_textpage_ocr(language=self.language, dpi=self.dpi, full=True)
        return page.get_text("words", textpage=textpage, sort=True)


def get_ocr_engine(enabled: bool, language: str) -> OcrEngine | None:
    if enabled and TesseractOcr.is_installed():
        return TesseractOcr(language=language)
    return None
