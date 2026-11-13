from typing import Literal

from pydantic import BaseModel

PageMethod = Literal["text", "ocr", "none"]
DocumentMethod = Literal["text", "ocr", "mixed", "none"]


class TextCell(BaseModel):
    x0: float
    x1: float
    text: str


class TextLine(BaseModel):
    """One visual row of a page; cells are separated by wide horizontal gaps."""

    y: float  # vertical centre, points from the top of the page
    cells: list[TextCell]

    @property
    def text(self) -> str:
        return "  ".join(c.text for c in self.cells)


class PageText(BaseModel):
    page_number: int  # 1-based, for evidence references
    text: str  # rows joined by newlines, cells by two spaces
    lines: list[TextLine] = []
    char_count: int
    method: PageMethod
    has_images: bool


class ExtractionResult(BaseModel):
    method: DocumentMethod
    page_count: int
    pages: list[PageText]
    warnings: list[str]
    extractor: str
    ocr_available: bool

    @property
    def has_text(self) -> bool:
        return any(p.method != "none" for p in self.pages)


class ExtractionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
