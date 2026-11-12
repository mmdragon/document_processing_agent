from typing import Literal

from pydantic import BaseModel

PageMethod = Literal["text", "ocr", "none"]
DocumentMethod = Literal["text", "ocr", "mixed", "none"]


class PageText(BaseModel):
    page_number: int  # 1-based, for evidence references
    text: str
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
