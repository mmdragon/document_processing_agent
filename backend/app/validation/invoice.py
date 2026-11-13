"""Deterministic invoice validation (InvoiceValidator.validate).

Pure Python rules, no model calls. Every rule records a check outcome so the UI can
show what was verified, not only what failed. Possible duplicates are similarity
flags for a human to check, never a finding of fraud.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.schemas.invoice import (
    DuplicateCandidate,
    InvoiceFields,
    ValidationCheck,
    ValidationIssue,
    ValidationResult,
)

# Absolute tolerance for money comparisons, to absorb rounding on the document.
TOLERANCE = Decimal("0.01")
CENT = Decimal("0.01")

_REQUIRED = (
    ("vendor_name", "missing_vendor_name", "error", "Vendor name"),
    ("invoice_number", "missing_invoice_number", "error", "Invoice number"),
    ("invoice_date", "missing_invoice_date", "error", "Invoice date"),
    ("due_date", "missing_due_date", "warning", "Due date"),
    ("currency", "missing_currency", "warning", "Currency"),
    ("total", "missing_total", "error", "Total"),
)


def _money(d: Decimal) -> str:
    return f"{d:,.2f}"


class InvoiceValidator:
    def validate(
        self,
        fields: InvoiceFields,
        *,
        extraction_method: str,
        duplicates: list[DuplicateCandidate] | None = None,
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        checks: list[ValidationCheck] = []

        if extraction_method == "none":
            issues.append(
                ValidationIssue(
                    code="ocr_required",
                    severity="warning",
                    message=(
                        "The document has no readable text layer. Install Tesseract OCR or "
                        "enter the fields manually."
                    ),
                )
            )
            checks.append(
                ValidationCheck(
                    name="all_checks", outcome="skipped", detail="No text was extracted."
                )
            )
            return ValidationResult(issues=issues, checks=checks, fields_needing_review=[])

        if extraction_method in ("ocr", "mixed"):
            issues.append(
                ValidationIssue(
                    code="ocr_text",
                    severity="info",
                    message="Some values were read by OCR; compare them with the document.",
                )
            )

        self._required(fields, issues, checks)
        self._dates(fields, issues, checks)
        self._line_items(fields, issues, checks)
        self._subtotal(fields, issues, checks)
        self._total(fields, issues, checks)
        self._duplicates(duplicates or [], issues, checks)

        review = [name for name, f in fields.scalar_fields().items() if f.needs_review]
        if review:
            issues.append(
                ValidationIssue(
                    code="fields_need_review",
                    severity="warning",
                    message="Some values are ambiguous or low-confidence: " + ", ".join(review),
                    details={"fields": review},
                )
            )
        return ValidationResult(issues=issues, checks=checks, fields_needing_review=review)

    # ------------------------------------------------------------------ rules

    @staticmethod
    def _required(fields, issues, checks) -> None:
        missing = []
        for name, code, severity, label in _REQUIRED:
            f = getattr(fields, name)
            if f.status != "missing":
                continue
            missing.append(name)
            message = f"{label} was not found on the document."
            if name == "due_date" and fields.payment_terms.value:
                message += (
                    f" Payment terms '{fields.payment_terms.value}' are printed, but the due "
                    "date is not calculated automatically."
                )
            issues.append(
                ValidationIssue(code=code, severity=severity, field=name, message=message)
            )
        checks.append(
            ValidationCheck(
                name="required_fields",
                outcome="failed" if missing else "passed",
                detail=f"Missing: {', '.join(missing)}"
                if missing
                else "All required fields present.",
            )
        )

    @staticmethod
    def _dates(fields, issues, checks) -> None:
        problems = 0
        for name in ("invoice_date", "due_date"):
            f = getattr(fields, name)
            if f.status == "ambiguous":
                problems += 1
                issues.append(
                    ValidationIssue(
                        code="ambiguous_date",
                        severity="warning",
                        field=name,
                        message=f"{name.replace('_', ' ').capitalize()}: {f.note}",
                        details={"raw": f.raw},
                    )
                )
            elif f.status == "unparseable":
                problems += 1
                issues.append(
                    ValidationIssue(
                        code="unparseable_date",
                        severity="warning",
                        field=name,
                        message=f"{name.replace('_', ' ').capitalize()}: {f.note}",
                        details={"raw": f.raw},
                    )
                )
        inv, due = fields.invoice_date.value, fields.due_date.value
        if inv and due and due < inv:
            problems += 1
            issues.append(
                ValidationIssue(
                    code="due_before_invoice_date",
                    severity="warning",
                    field="due_date",
                    message=f"Due date {due} is before the invoice date {inv}.",
                )
            )
        checks.append(
            ValidationCheck(
                name="dates",
                outcome="failed" if problems else "passed",
                detail=f"{problems} date problem(s)."
                if problems
                else "Dates are parseable and ordered.",
            )
        )

    @staticmethod
    def _line_items(fields, issues, checks) -> None:
        if not fields.line_items:
            issues.append(
                ValidationIssue(
                    code="no_line_items",
                    severity="warning",
                    field="line_items",
                    message="No line items could be read.",
                )
            )
            checks.append(
                ValidationCheck(name="line_item_math", outcome="skipped", detail="No line items.")
            )
            return
        bad = 0
        for n, item in enumerate(fields.line_items, start=1):
            expected = (item.quantity * item.unit_price).quantize(CENT, rounding=ROUND_HALF_UP)
            if abs(expected - item.amount) > TOLERANCE:
                bad += 1
                issues.append(
                    ValidationIssue(
                        code="line_item_amount_mismatch",
                        severity="error",
                        field="line_items",
                        message=(
                            f"Line {n} '{item.description}': {item.quantity} × "
                            f"{_money(item.unit_price)} = {_money(expected)}, but "
                            f"{_money(item.amount)} is printed."
                        ),
                        details={
                            "line": n,
                            "expected": str(expected),
                            "printed": str(item.amount),
                            "page": item.evidence.page_number,
                        },
                    )
                )
        checks.append(
            ValidationCheck(
                name="line_item_math",
                outcome="failed" if bad else "passed",
                detail=f"{bad} of {len(fields.line_items)} lines disagree with qty × unit price."
                if bad
                else f"All {len(fields.line_items)} lines equal qty × unit price.",
            )
        )

    @staticmethod
    def _subtotal(fields, issues, checks) -> None:
        if fields.subtotal.value is None or not fields.line_items:
            checks.append(
                ValidationCheck(
                    name="subtotal",
                    outcome="skipped",
                    detail="Needs both a printed subtotal and line items.",
                )
            )
            return
        computed = sum((i.amount for i in fields.line_items), Decimal("0"))
        printed = fields.subtotal.value
        if abs(computed - printed) > TOLERANCE:
            issues.append(
                ValidationIssue(
                    code="subtotal_mismatch",
                    severity="error",
                    field="subtotal",
                    message=(
                        f"Line items add up to {_money(computed)}, but the subtotal shows "
                        f"{_money(printed)}."
                    ),
                    details={"computed": str(computed), "printed": str(printed)},
                )
            )
            outcome = "failed"
        else:
            outcome = "passed"
        checks.append(
            ValidationCheck(
                name="subtotal",
                outcome=outcome,
                detail=f"Sum of line amounts {_money(computed)} vs printed {_money(printed)}.",
            )
        )

    @staticmethod
    def _total(fields, issues, checks) -> None:
        if fields.total.value is None:
            checks.append(
                ValidationCheck(name="total", outcome="skipped", detail="No printed total.")
            )
            return
        if fields.subtotal.value is not None:
            base, base_label = fields.subtotal.value, "subtotal"
        elif fields.line_items:
            base = sum((i.amount for i in fields.line_items), Decimal("0"))
            base_label = "sum of line items (no subtotal printed)"
        else:
            checks.append(
                ValidationCheck(
                    name="total", outcome="skipped", detail="No subtotal or line items."
                )
            )
            return
        discount = fields.discount.value or Decimal("0")
        tax = fields.tax.value or Decimal("0")
        shipping = fields.shipping.value or Decimal("0")
        expected = base - discount + tax + shipping
        printed = fields.total.value
        formula = (
            f"{base_label} {_money(base)} − discount {_money(discount)} + tax {_money(tax)} "
            f"+ shipping {_money(shipping)} = {_money(expected)}"
        )
        absent = [n for n in ("discount", "tax", "shipping") if getattr(fields, n).value is None]
        if abs(expected - printed) > TOLERANCE:
            issues.append(
                ValidationIssue(
                    code="total_mismatch",
                    severity="error",
                    field="total",
                    message=f"{formula}, but the total shows {_money(printed)}.",
                    details={
                        "expected": str(expected),
                        "printed": str(printed),
                        "treated_as_zero": absent,
                    },
                )
            )
            outcome = "failed"
        else:
            outcome = "passed"
        detail = formula + (f" (not printed, treated as 0: {', '.join(absent)})" if absent else "")
        checks.append(ValidationCheck(name="total", outcome=outcome, detail=detail))

    @staticmethod
    def _duplicates(duplicates, issues, checks) -> None:
        for dup in duplicates:
            issues.append(
                ValidationIssue(
                    code="possible_duplicate",
                    severity="warning",
                    message=(
                        f"Possible duplicate of '{dup.original_filename}' (uploaded "
                        f"{dup.uploaded_at[:10]}): "
                        + (
                            "the same file was uploaded before."
                            if dup.reason == "identical_file"
                            else "same vendor and invoice number."
                        )
                        + " This is a similarity flag for a person to check, not a finding "
                        "of fraud."
                    ),
                    details=dup.model_dump(),
                )
            )
        checks.append(
            ValidationCheck(
                name="duplicates",
                outcome="failed" if duplicates else "passed",
                detail=(
                    f"{len(duplicates)} earlier document(s) match by vendor + invoice "
                    "number or file."
                )
                if duplicates
                else "No earlier document matches by vendor + invoice number or file.",
            )
        )
