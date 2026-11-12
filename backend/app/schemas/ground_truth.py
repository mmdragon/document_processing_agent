"""Ground-truth schema for the synthetic invoice dataset.

Ground truth records what is *printed on the document*, not what "should" be true:
an invoice with an arithmetic error stores the wrong printed total, and the error is
listed in ``expected_issues``. Missing fields are ``None``; they are never filled in.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

RenderMode = Literal["text", "scan", "low_quality_scan"]

IssueCode = Literal[
    "missing_invoice_number",
    "missing_due_date",
    "line_item_amount_mismatch",
    "subtotal_mismatch",
    "total_mismatch",
    "possible_duplicate",
    "ambiguous_date",
    "ocr_required",
    "low_quality_scan",
]


class GroundTruthLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Decimal
    unit_price: Decimal
    amount: Decimal


class GroundTruthFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str
    vendor_address: str
    invoice_number: str | None
    invoice_date: date | None
    invoice_date_raw: str | None
    due_date: date | None
    due_date_raw: str | None
    currency: str
    line_items: list[GroundTruthLineItem]
    subtotal: Decimal
    discount: Decimal | None
    tax: Decimal | None
    shipping: Decimal | None
    total: Decimal
    purchase_order_number: str | None
    payment_terms: str | None


class GroundTruth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic: Literal[True]
    document_id: str
    file_name: str
    scenario: str
    description: str
    render_mode: RenderMode
    expected_extraction_method: Literal["text", "ocr"]
    expected_issues: list[IssueCode]
    duplicate_of: str | None = None
    fields: GroundTruthFields
