"""Reviewer corrections and the validation that runs on corrected values.

Extracted values are never overwritten. Corrections are stored as an audit list and
applied on top of a copy of the extracted fields whenever validation runs.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation

from app.normalization.parsers import invoice_number_key, vendor_key
from app.repositories.documents import DocumentRepository
from app.schemas.documents import Correction, CorrectionRequest, ProcessingStatus
from app.schemas.invoice import ExtractedField, InvoiceFields, ValidationResult
from app.validation.invoice import InvoiceValidator

DATE_FIELDS = {"invoice_date", "due_date"}
MONEY_FIELDS = {"subtotal", "discount", "tax", "shipping", "total"}


class CorrectionError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def parse_correction(field: str, value: str | None):
    """Turn reviewer text into a typed value, strictly. Raises CorrectionError."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    if field in DATE_FIELDS:
        try:
            return date.fromisoformat(text)
        except ValueError as exc:
            raise CorrectionError(field, "Use the format YYYY-MM-DD.") from exc
    if field in MONEY_FIELDS:
        if not re.fullmatch(r"\d{1,12}(\.\d{1,2})?", text):
            raise CorrectionError(field, "Use a plain amount like 1234.50 (no symbols).")
        try:
            return Decimal(text)
        except InvalidOperation as exc:  # pragma: no cover - regex guards this
            raise CorrectionError(field, "Not a valid amount.") from exc
    if field == "currency":
        if not re.fullmatch(r"[A-Za-z]{3}", text):
            raise CorrectionError(field, "Use a 3-letter currency code like USD.")
        return text.upper()
    return " ".join(text.split())


def _as_text(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def build_corrections(fields: InvoiceFields, requests: list[CorrectionRequest]) -> list[Correction]:
    now = datetime.now(UTC)
    records = []
    for req in requests:
        typed = parse_correction(req.field, req.value)
        original: ExtractedField = getattr(fields, req.field)
        records.append(
            Correction(
                field=req.field,
                original_value=_as_text(original.value)
                if original.value is not None
                else original.raw,
                original_status=original.status,
                corrected_value=_as_text(typed),
                note=req.note,
                corrected_at=now,
            )
        )
    return records


def apply_corrections(fields: InvoiceFields, corrections: list[Correction]) -> InvoiceFields:
    """Return a copy of ``fields`` with the latest correction per field applied."""
    effective = fields.model_copy(deep=True)
    latest: dict[str, Correction] = {}
    for c in corrections:
        latest[c.field] = c
    for name, c in latest.items():
        original: ExtractedField = getattr(fields, name)
        typed = parse_correction(name, c.corrected_value)
        setattr(
            effective,
            name,
            ExtractedField(
                value=typed,
                raw=original.raw,
                status="found" if typed is not None else "missing",
                confidence=1.0 if typed is not None else 0.0,
                evidence=original.evidence,
                note="Value set by a reviewer." if typed is not None else "Cleared by a reviewer.",
                corrected=True,
            ),
        )
    return effective


def validate_and_store(
    document_id: str,
    repo: DocumentRepository,
    *,
    fields: InvoiceFields,
    corrections: list[Correction],
    extraction_method: str,
    validator: InvoiceValidator | None = None,
) -> tuple[ProcessingStatus, ValidationResult, str | None, str | None]:
    """Validate corrected fields, look up duplicates, and work out the status.

    Returns (status, validation, vendor_key, invoice_key) without saving, so callers
    can store them with the rest of their update.
    """
    validator = validator or InvoiceValidator()
    effective = apply_corrections(fields, corrections)
    method = extraction_method
    if method == "none" and corrections:
        method = "manual"  # no text, but a reviewer entered values: check them
    v_key = vendor_key(effective.vendor_name.value)
    i_key = invoice_number_key(effective.invoice_number.value)
    duplicates = repo.find_duplicates(
        document_id,
        vendor_key=v_key,
        invoice_key=i_key,
        sha256=repo.get_sha256(document_id) or "",
    )
    validation = validator.validate(effective, extraction_method=method, duplicates=duplicates)
    status: ProcessingStatus
    if method == "none":
        status = "needs_ocr"
    elif validation.needs_review:
        status = "needs_review"
    else:
        status = "processed"
    return status, validation, v_key, i_key
