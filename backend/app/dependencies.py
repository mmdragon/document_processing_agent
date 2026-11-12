from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.extraction.ocr import get_ocr_engine
from app.extraction.pdf import PyMuPDFExtractor
from app.repositories.documents import DocumentRepository

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_repository(settings: SettingsDep) -> DocumentRepository:
    return DocumentRepository(settings.database_path)


def get_extractor(settings: SettingsDep) -> PyMuPDFExtractor:
    return PyMuPDFExtractor(
        ocr=get_ocr_engine(settings.ocr_enabled, settings.ocr_language),
        min_chars_per_page=settings.min_text_chars_per_page,
        max_pages=settings.max_pages,
    )


RepositoryDep = Annotated[DocumentRepository, Depends(get_repository)]
ExtractorDep = Annotated[PyMuPDFExtractor, Depends(get_extractor)]
