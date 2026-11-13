from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    reviewed_at: datetime | None = None


# Scalar invoice fields a reviewer may correct (line items are read-only for now).
CorrectableField = Literal[
    "vendor_name",
    "vendor_address",
    "invoice_number",
    "invoice_date",
    "due_date",
    "currency",
    "subtotal",
    "discount",
    "tax",
    "shipping",
    "total",
    "purchase_order_number",
    "payment_terms",
]


class Correction(BaseModel):
    """An audit record: the extracted value is kept; the correction sits beside it."""

    field: CorrectableField
    original_value: str | None
    original_status: str
    corrected_value: str | None
    note: str | None = None
    corrected_at: datetime


class CorrectionRequest(BaseModel):
    field: CorrectableField
    # Text as typed. Dates: YYYY-MM-DD. Amounts: plain decimal (e.g. 1234.50).
    # Currency: 3-letter code. null clears the value.
    value: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)


class CorrectionsRequest(BaseModel):
    corrections: list[CorrectionRequest] = Field(min_length=1, max_length=20)


class ReviewRequest(BaseModel):
    # true marks the document reviewed; false reopens it.
    reviewed: bool = True
    note: str | None = Field(default=None, max_length=1000)


class DocumentDetail(DocumentSummary):
    extraction: ExtractionResult | None = None
    # Values exactly as extracted; never modified by corrections.
    fields: InvoiceFields | None = None
    corrections: list[Correction] = []
    # Validation runs on the extracted values with the latest corrections applied.
    validation: ValidationResult | None = None
    review_note: str | None = None
