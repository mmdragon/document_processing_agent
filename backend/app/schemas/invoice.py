"""Typed invoice fields with evidence, and deterministic validation results.

Every extracted value carries where it came from (page + line text) and a status.
Missing or ambiguous values stay ``None``; nothing is guessed or filled in.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

# found        -> value read from the document
# missing      -> no value on the document
# ambiguous    -> text found but it has more than one reasonable reading (value is None)
# unparseable  -> text found but it could not be interpreted (value is None)
FieldStatus = Literal["found", "missing", "ambiguous", "unparseable"]

REVIEW_CONFIDENCE = 0.8  # fields below this are flagged for human review


class Evidence(BaseModel):
    page_number: int
    line: str  # the source line as extracted (not model-generated)
    method: Literal["text", "ocr"]


class ExtractedField(BaseModel, Generic[T]):
    value: T | None = None
    raw: str | None = None  # exact text the value was read from
    status: FieldStatus = "missing"
    confidence: float = 0.0
    evidence: Evidence | None = None
    note: str | None = None
    corrected: bool = False  # True when a reviewer supplied the value

    @property
    def needs_review(self) -> bool:
        return self.status in ("ambiguous", "unparseable") or (
            self.status == "found" and self.confidence < REVIEW_CONFIDENCE
        )


class LineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal
    evidence: Evidence


class InvoiceFields(BaseModel):
    vendor_name: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    vendor_address: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    invoice_number: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    invoice_date: ExtractedField[date] = Field(default_factory=ExtractedField[date])
    due_date: ExtractedField[date] = Field(default_factory=ExtractedField[date])
    currency: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    line_items: list[LineItem] = []
    subtotal: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    discount: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    tax: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    shipping: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    total: ExtractedField[Decimal] = Field(default_factory=ExtractedField[Decimal])
    purchase_order_number: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    payment_terms: ExtractedField[str] = Field(default_factory=ExtractedField[str])
    # Problems the extractor hit (e.g. table rows it could not parse).
    extraction_notes: list[str] = []

    def scalar_fields(self) -> dict[str, ExtractedField]:
        return {name: value for name, value in self if isinstance(value, ExtractedField)}


Severity = Literal["error", "warning", "info"]


class ValidationIssue(BaseModel):
    code: str
    severity: Severity
    field: str | None = None
    message: str
    details: dict[str, Any] = {}


class ValidationCheck(BaseModel):
    name: str
    outcome: Literal["passed", "failed", "skipped"]
    detail: str


class DuplicateCandidate(BaseModel):
    reason: Literal["same_vendor_and_number", "identical_file"]
    document_id: str
    original_filename: str
    uploaded_at: str
    vendor_name: str | None
    invoice_number: str | None
    sha256: str


class ValidationResult(BaseModel):
    issues: list[ValidationIssue]
    checks: list[ValidationCheck]
    fields_needing_review: list[str]

    @property
    def needs_review(self) -> bool:
        return bool(self.fields_needing_review) or any(
            i.severity in ("error", "warning") for i in self.issues
        )
