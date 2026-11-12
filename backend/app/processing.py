"""Run extraction for a stored document and record the outcome.

Logs carry document IDs and statuses only, never document text.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.extraction.models import ExtractionError
from app.extraction.pdf import PyMuPDFExtractor
from app.repositories.documents import DocumentRepository
from app.schemas.documents import DocumentDetail

logger = logging.getLogger(__name__)


def process_document(
    document_id: str,
    stored_path: Path,
    repo: DocumentRepository,
    extractor: PyMuPDFExtractor,
) -> DocumentDetail:
    repo.set_status(document_id, "processing")
    try:
        result = extractor.extract_text(stored_path)
    except ExtractionError as exc:
        repo.save_extraction(document_id, status="failed", extraction=None, error=exc.message)
        logger.warning("document %s failed extraction: %s", document_id, exc.code)
    except Exception as exc:  # never leave a document stuck in "processing"
        repo.save_extraction(
            document_id, status="failed", extraction=None, error="Unexpected extraction error."
        )
        logger.exception("document %s unexpected error: %s", document_id, type(exc).__name__)
    else:
        status = "extracted" if result.has_text else "needs_ocr"
        repo.save_extraction(document_id, status=status, extraction=result, error=None)
        logger.info(
            "document %s %s: method=%s pages=%d",
            document_id,
            status,
            result.method,
            result.page_count,
        )

    detail = repo.get_detail(document_id)
    assert detail is not None
    return detail
