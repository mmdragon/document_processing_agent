"""Processing pipeline: text extraction -> field extraction -> validation.

Logs carry document IDs, statuses and issue codes only, never document text or values.
"""

from __future__ import annotations

import logging
from pathlib import Path

from app.extraction.fields import RuleBasedFieldExtractor
from app.extraction.models import ExtractionError
from app.extraction.pdf import PyMuPDFExtractor
from app.normalization.parsers import invoice_number_key, vendor_key
from app.repositories.documents import DocumentRepository
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
        v_key = vendor_key(fields.vendor_name.value)
        i_key = invoice_number_key(fields.invoice_number.value)
        sha = repo.get_sha256(document_id) or ""
        duplicates = repo.find_duplicates(
            document_id, vendor_key=v_key, invoice_key=i_key, sha256=sha
        )
        validation = validator.validate(
            fields, extraction_method=extraction.method, duplicates=duplicates
        )
    except Exception as exc:
        logger.exception(
            "document %s unexpected validation error: %s", document_id, type(exc).__name__
        )
        return fail("Unexpected error while reading invoice fields.")

    if not extraction.has_text:
        status = "needs_ocr"
    elif validation.needs_review:
        status = "needs_review"
    else:
        status = "processed"

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
