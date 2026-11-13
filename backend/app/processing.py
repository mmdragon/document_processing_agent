"""Processing pipeline: text extraction -> field extraction -> validation.

Logs carry document IDs, statuses and issue codes only, never document text or values.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.extraction.fields import RuleBasedFieldExtractor
from app.extraction.models import ExtractionError
from app.extraction.pdf import PyMuPDFExtractor
from app.repositories.documents import DocumentRepository
from app.review import validate_and_store
from app.schemas.documents import DocumentDetail
from app.validation.invoice import InvoiceValidator

logger = logging.getLogger(__name__)


def process_document(
    document_id: str,
    stored_path: Path,
    repo: DocumentRepository,
    extractor: PyMuPDFExtractor,
    field_extractor: RuleBasedFieldExtractor | None = None,
    validator: InvoiceValidator | None = None,
) -> DocumentDetail:
    field_extractor = field_extractor or RuleBasedFieldExtractor()
    validator = validator or InvoiceValidator()
    repo.set_status(document_id, "processing")

    def fail(message: str) -> DocumentDetail:
        repo.save_results(
            document_id,
            status="failed",
            extraction=None,
            fields=None,
            validation=None,
            vendor_key=None,
            invoice_key=None,
            error=message,
        )
        detail = repo.get_detail(document_id)
        assert detail is not None
        return detail

    try:
        extraction = extractor.extract_text(stored_path)
    except ExtractionError as exc:
        logger.warning("document %s failed extraction: %s", document_id, exc.code)
        return fail(exc.message)
    except Exception as exc:  # never leave a document stuck in "processing"
        logger.exception(
            "document %s unexpected extraction error: %s", document_id, type(exc).__name__
        )
        return fail("Unexpected extraction error.")

    try:
        fields = field_extractor.extract_fields(extraction)
        existing = repo.get_detail(document_id)
        corrections = existing.corrections if existing else []
        status, validation, v_key, i_key = validate_and_store(
            document_id,
            repo,
            fields=fields,
            corrections=corrections,
            extraction_method=extraction.method,
            validator=validator,
        )
    except Exception as exc:
        logger.exception(
            "document %s unexpected validation error: %s", document_id, type(exc).__name__
        )
        return fail("Unexpected error while reading invoice fields.")

    repo.save_results(
        document_id,
        status=status,
        extraction=extraction,
        fields=fields,
        validation=validation,
        vendor_key=v_key,
        invoice_key=i_key,
        error=None,
    )
    logger.info(
        "document %s %s: method=%s pages=%d issues=%s",
        document_id,
        status,
        extraction.method,
        extraction.page_count,
        sorted({i.code for i in validation.issues}),
    )
    detail = repo.get_detail(document_id)
    assert detail is not None
    return detail
