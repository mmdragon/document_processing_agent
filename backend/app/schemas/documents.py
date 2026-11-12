from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.extraction.models import DocumentMethod, ExtractionResult

# uploaded   -> stored and validated, not processed yet
# processing -> extraction running
# extracted  -> text extracted (text layer and/or OCR)
# needs_ocr  -> no usable text layer and OCR is not available
# failed     -> processing error (see `error`)
# reviewed   -> a human marked it reviewed (Phase 5)
ProcessingStatus = Literal["uploaded", "processing", "extracted", "needs_ocr", "failed", "reviewed"]


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
