"""Page-aware text extraction with PyMuPDF, falling back to optional OCR per page."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.extraction.models import (
    DocumentMethod,
    ExtractionError,
    ExtractionResult,
    PageText,
)
from app.extraction.ocr import OcrEngine

pymupdf.TOOLS.mupdf_display_errors(False)

_IMAGE_TYPES = {".png", ".jpg", ".jpeg"}


def _open(path: Path) -> pymupdf.Document:
    """Open a PDF directly, or wrap an image in a one-page PDF (in memory)."""
    ext = path.suffix.lower()
    if not path.is_file():
        raise ExtractionError("file_missing", "Stored file is missing.")
    try:
        if ext in _IMAGE_TYPES:
            with pymupdf.open(path) as img:
                pdf_bytes = img.convert_to_pdf()
            return pymupdf.open("pdf", pdf_bytes)
        return pymupdf.open(path, filetype="pdf")
    except Exception as exc:
        raise ExtractionError("unreadable_file", "The file could not be read.") from exc


class PyMuPDFExtractor:
    """DocumentExtractor: extract_text(path) -> ExtractionResult."""

    def __init__(
        self,
        *,
        ocr: OcrEngine | None,
        min_chars_per_page: int = 20,
        max_pages: int = 50,
    ) -> None:
        self.ocr = ocr
        self.min_chars = min_chars_per_page
        self.max_pages = max_pages

    def extract_text(self, path: Path) -> ExtractionResult:
        warnings: list[str] = []
        pages: list[PageText] = []
        with _open(path) as doc:
            if doc.needs_pass:
                raise ExtractionError("encrypted_pdf", "Password-protected PDFs are not supported.")
            if doc.page_count == 0:
                raise ExtractionError("no_pages", "The document has no pages.")
            if doc.page_count > self.max_pages:
                raise ExtractionError(
                    "too_many_pages", f"Documents are limited to {self.max_pages} pages."
                )
            for index, page in enumerate(doc):
                pages.append(self._extract_page(page, index + 1, warnings))
            page_count = doc.page_count

        methods = {p.method for p in pages} - {"none"}
        method: DocumentMethod
        if not methods:
            method = "none"
        elif len(methods) == 1:
            method = methods.pop()  # type: ignore[assignment]
        else:
            method = "mixed"

        return ExtractionResult(
            method=method,
            page_count=page_count,
            pages=pages,
            warnings=warnings,
            extractor=f"pymupdf {pymupdf.VersionBind}"
            + (f" + {self.ocr.name}" if self.ocr else ""),
            ocr_available=self.ocr is not None,
        )

    def _extract_page(self, page: pymupdf.Page, page_number: int, warnings: list[str]) -> PageText:
        has_images = bool(page.get_images(full=False))
        text = page.get_text("text", sort=True).strip()
        if len(text) >= self.min_chars:
            return PageText(
                page_number=page_number,
                text=text,
                char_count=len(text),
                method="text",
                has_images=has_images,
            )

        if self.ocr is None:
            warnings.append(f"Page {page_number}: no usable text layer and OCR is not available.")
            return PageText(
                page_number=page_number,
                text=text,
                char_count=len(text),
                method="none",
                has_images=has_images,
            )

        try:
            ocr_text = self.ocr.page_text(page)
        except Exception:
            warnings.append(f"Page {page_number}: OCR failed.")
            ocr_text = ""
        if len(ocr_text) < self.min_chars:
            warnings.append(f"Page {page_number}: OCR found little or no text.")
            return PageText(
                page_number=page_number,
                text=ocr_text,
                char_count=len(ocr_text),
                method="none",
                has_images=has_images,
            )
        warnings.append(f"Page {page_number}: text came from OCR and may contain errors.")
        return PageText(
            page_number=page_number,
            text=ocr_text,
            char_count=len(ocr_text),
            method="ocr",
            has_images=has_images,
        )
