from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.extraction.models import DocumentMethod, ExtractionResult
from app.schemas.invoice import InvoiceFields, ValidationResult

# uploaded     -> stored and checked, not processed yet
# processing   -> extraction + validation running
# processed    -> fields extracted, every check passed, nothing needs review
# needs_review -> validation issues or ambiguous / low-confidence fields
# needs_ocr    -> no usable text layer and OCR is not available
# failed       -> processing error (see `error`)
# reviewed     -> a person marked it reviewed (Phase 5)
ProcessingStatus = Literal[
    "uploaded", "processing", "processed", "needs_review", "needs_ocr", "failed", "reviewed"
]


class DocumentSummary(BaseModel):
    document_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    page_count: int
    uploaded_at: datetime
    updated_at: datetime
    status: ProcessingStatus
    extraction_method: DocumentMethod | None = None
    error: str | None = None


class DocumentDetail(DocumentSummary):
    extraction: ExtractionResult | None = None
    fields: InvoiceFields | None = None
    validation: ValidationResult | None = None
