"""Page-aware text extraction with PyMuPDF, falling back to optional OCR per page."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.extraction.models import (
    DocumentMethod,
    ExtractionError,
    ExtractionResult,
    PageMethod,
    PageText,
    TextCell,
    TextLine,
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
        lines = build_lines(page.get_text("words", sort=True))
        page_text = make_page(page_number, lines, "text", has_images)
        if page_text.char_count >= self.min_chars:
            return page_text

        if self.ocr is None:
            warnings.append(f"Page {page_number}: no usable text layer and OCR is not available.")
            return make_page(page_number, lines, "none", has_images)

        try:
            ocr_lines = build_lines(self.ocr.page_words(page))
        except Exception:
            warnings.append(f"Page {page_number}: OCR failed.")
            ocr_lines = []
        ocr_page = make_page(page_number, ocr_lines, "ocr", has_images)
        if ocr_page.char_count < self.min_chars:
            warnings.append(f"Page {page_number}: OCR found little or no text.")
            return make_page(page_number, ocr_lines, "none", has_images)
        warnings.append(f"Page {page_number}: text came from OCR and may contain errors.")
        return ocr_page


# Words closer than this (points) belong to the same cell; wider gaps start a new cell.
CELL_GAP = 8.0
# Words whose vertical centres differ by less than this (points) share a row.
ROW_TOLERANCE = 4.0


def build_lines(words: list[tuple]) -> list[TextLine]:
    """Group word boxes into visual rows and cells, top to bottom, left to right."""
    items = sorted(
        ((w[0], w[2], (w[1] + w[3]) / 2, str(w[4])) for w in words if str(w[4]).strip()),
        key=lambda t: (t[2], t[0]),
    )
    rows: list[list[tuple[float, float, float, str]]] = []
    for item in items:
        if rows and abs(item[2] - rows[-1][0][2]) < ROW_TOLERANCE:
            rows[-1].append(item)
        else:
            rows.append([item])

    lines: list[TextLine] = []
    for row in rows:
        row.sort(key=lambda t: t[0])
        cells: list[TextCell] = []
        for x0, x1, _, word in row:
            if cells and x0 - cells[-1].x1 <= CELL_GAP:
                cells[-1] = TextCell(x0=cells[-1].x0, x1=x1, text=f"{cells[-1].text} {word}")
            else:
                cells.append(TextCell(x0=x0, x1=x1, text=word))
        y = sum(t[2] for t in row) / len(row)
        lines.append(TextLine(y=round(y, 1), cells=cells))
    return lines


def make_page(
    page_number: int, lines: list[TextLine], method: PageMethod, has_images: bool
) -> PageText:
    text = "\n".join(line.text for line in lines)
    return PageText(
        page_number=page_number,
        text=text,
        lines=lines,
        char_count=len(text),
        method=method,
        has_images=has_images,
    )
