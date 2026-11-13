from datetime import date
from decimal import Decimal

from app.schemas.invoice import (
    DuplicateCandidate,
    Evidence,
    ExtractedField,
    InvoiceFields,
    LineItem,
)
from app.validation.invoice import InvoiceValidator

EV = Evidence(page_number=1, line="synthetic line", method="text")


def found(value, confidence=0.95):
    return ExtractedField(
        value=value, raw=str(value), status="found", confidence=confidence, evidence=EV
    )


def item(qty, unit, amount):
    return LineItem(
        description="Widget",
        quantity=Decimal(qty),
        unit_price=Decimal(unit),
        amount=Decimal(amount),
        evidence=EV,
    )


def good_fields(**overrides) -> InvoiceFields:
    f = InvoiceFields(
        vendor_name=found("Fictional Vendor"),
        invoice_number=found("FV-1"),
        invoice_date=found(date(2026, 3, 1)),
        due_date=found(date(2026, 3, 31)),
        currency=found("USD"),
        line_items=[item("2", "10.00", "20.00"), item("1", "5.55", "5.55")],
        subtotal=found(Decimal("25.55")),
        tax=found(Decimal("2.04")),
        shipping=found(Decimal("4.00")),
        discount=found(Decimal("1.55")),
        total=found(Decimal("30.04")),
    )
    for k, v in overrides.items():
        setattr(f, k, v)
    return f


def codes(result):
    return [i.code for i in result.issues]


def run(fields, method="text", duplicates=None):
    return InvoiceValidator().validate(fields, extraction_method=method, duplicates=duplicates)


def test_clean_invoice_passes_everything():
    r = run(good_fields())
    assert codes(r) == []
    assert not r.needs_review
    assert {c.name: c.outcome for c in r.checks} == {
        "required_fields": "passed",
        "dates": "passed",
        "line_item_math": "passed",
        "subtotal": "passed",
        "total": "passed",
        "duplicates": "passed",
    }


def test_one_cent_rounding_is_tolerated_but_two_is_not():
    assert "total_mismatch" not in codes(run(good_fields(total=found(Decimal("30.05")))))
    assert "total_mismatch" in codes(run(good_fields(total=found(Decimal("30.06")))))


def test_line_item_half_up_rounding():
    # 3 x 0.125 = 0.375 -> 0.38 (half up)
    f = good_fields(line_items=[item("3", "0.125", "0.38")], subtotal=found(Decimal("0.38")))
    f.total = found(Decimal("0.38") - Decimal("1.55") + Decimal("2.04") + Decimal("4.00"))
    assert codes(run(f)) == []


def test_mismatches_are_errors_with_details():
    f = good_fields(
        line_items=[item("2", "10.00", "21.00"), item("1", "5.55", "5.55")],
        subtotal=found(Decimal("99.00")),
    )
    r = run(f)
    by_code = {i.code: i for i in r.issues}
    assert by_code["line_item_amount_mismatch"].severity == "error"
    assert by_code["line_item_amount_mismatch"].details["expected"] == "20.00"
    assert by_code["subtotal_mismatch"].details["computed"] == "26.55"
    assert "total_mismatch" in by_code


def test_total_uses_line_items_when_subtotal_missing():
    f = good_fields(subtotal=ExtractedField())
    r = run(f)
    assert "total_mismatch" not in codes(r)
    total_check = next(c for c in r.checks if c.name == "total")
    assert "no subtotal printed" in total_check.detail
    assert next(c for c in r.checks if c.name == "subtotal").outcome == "skipped"


def test_missing_optional_components_are_reported_as_zero():
    f = good_fields(discount=ExtractedField(), tax=ExtractedField(), shipping=ExtractedField())
    f.total = found(Decimal("25.55"))
    r = run(f)
    assert codes(r) == []
    assert (
        "treated as 0: discount, tax, shipping"
        in next(c for c in r.checks if c.name == "total").detail
    )


def test_missing_required_fields():
    f = good_fields(
        invoice_number=ExtractedField(),
        due_date=ExtractedField(),
        total=ExtractedField(),
        payment_terms=found("Net 30"),
    )
    r = run(f)
    assert {"missing_invoice_number", "missing_due_date", "missing_total"} <= set(codes(r))
    due = next(i for i in r.issues if i.code == "missing_due_date")
    assert "not calculated automatically" in due.message
    assert next(c for c in r.checks if c.name == "total").outcome == "skipped"


def test_ambiguous_and_out_of_order_dates():
    ambiguous = ExtractedField(
        value=None, raw="04/05/2026", status="ambiguous", note="x", evidence=EV
    )
    r = run(good_fields(invoice_date=ambiguous))
    assert "ambiguous_date" in codes(r)
    assert r.fields_needing_review == ["invoice_date"]

    r = run(good_fields(due_date=found(date(2026, 2, 1))))
    assert "due_before_invoice_date" in codes(r)


def test_low_confidence_field_needs_review():
    r = run(good_fields(currency=found("USD", confidence=0.6)))
    assert r.fields_needing_review == ["currency"]
    assert "fields_need_review" in codes(r)
    assert r.needs_review


def test_no_text_only_reports_ocr_required():
    r = run(InvoiceFields(), method="none")
    assert codes(r) == ["ocr_required"]
    assert [c.outcome for c in r.checks] == ["skipped"]


def test_ocr_text_is_noted():
    assert "ocr_text" in codes(run(good_fields(), method="mixed"))


def test_duplicate_wording_never_claims_fraud():
    dup = DuplicateCandidate(
        reason="same_vendor_and_number",
        document_id="a" * 32,
        original_filename="earlier.pdf",
        uploaded_at="2026-03-01T10:00:00+00:00",
        vendor_name="Fictional Vendor",
        invoice_number="FV-1",
        sha256="0" * 64,
    )
    issue = next(i for i in run(good_fields(), duplicates=[dup]).issues)
    assert issue.code == "possible_duplicate"
    assert issue.severity == "warning"
    assert "not a finding of fraud" in issue.message
    assert "fraudulent" not in issue.message.lower()
