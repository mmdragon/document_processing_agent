"""Deterministic, template-based explainer (no model, no network, no cost).

It restates extracted values and check results, adds clearly labelled
interpretations of each issue, and asks the reviewer about anything ambiguous.
It never computes new values (e.g. a due date from payment terms).
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from app.agents.models import (
    ExplainerInput,
    ExplanationDraft,
    ExplanationItem,
    ExplanationSection,
)
from app.schemas.invoice import ExtractedField, InvoiceFields, ValidationIssue

LABELS = {
    "vendor_name": "Vendor",
    "vendor_address": "Vendor address",
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "currency": "Currency",
    "purchase_order_number": "PO number",
    "payment_terms": "Payment terms",
    "subtotal": "Subtotal",
    "discount": "Discount",
    "tax": "Tax",
    "shipping": "Shipping",
    "total": "Total",
}
MONEY = {"subtotal", "discount", "tax", "shipping", "total"}
KEY_FIELDS = (
    "vendor_name",
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
)


def _fmt(name: str, value, currency: str | None) -> str:
    if value is None:
        return "—"
    if name in MONEY and isinstance(value, Decimal):
        return f"{value:,.2f}" + (f" {currency}" if currency else "")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _money(value: str | Decimal | None, currency: str | None) -> str:
    if value is None:
        return "—"
    return f"{Decimal(str(value)):,.2f}" + (f" {currency}" if currency else "")


class MockExplainer:
    name = "mock"
    model_generated = False

    def explain(self, data: ExplainerInput) -> ExplanationDraft:
        doc = data.document
        f = data.effective
        validation = doc.validation
        issues = validation.issues if validation else []

        if f is None or validation is None:
            return ExplanationDraft(
                summary="This document has not been processed yet, so there is nothing to explain.",
                sections=[],
                questions=[],
                next_steps=["Run extraction on the document."],
            )

        no_text = doc.extraction_method == "none"
        manual = no_text and bool(doc.corrections)
        currency = f.currency.value

        summary = self._summary(doc, f, issues, no_text, manual)
        sections = [
            self._extracted_section(f, currency, no_text, manual),
            self._checks_section(doc, issues),
        ]
        interpretations = self._interpretations(f, issues, currency)
        if interpretations:
            sections.append(ExplanationSection(title="What this might mean", items=interpretations))
        questions = self._questions(f, issues)
        return ExplanationDraft(
            summary=summary,
            sections=[s for s in sections if s.items],
            questions=questions,
            next_steps=self._next_steps(doc, issues, no_text, manual),
        )

    # ------------------------------------------------------------------ summary

    @staticmethod
    def _summary(doc, f: InvoiceFields, issues, no_text: bool, manual: bool) -> str:
        if no_text and not manual:
            return (
                "No text could be read from this document, so no fields were extracted. "
                "A person needs to enter the key fields, or OCR needs to be enabled."
            )
        vendor = f.vendor_name.value or "an unidentified vendor"
        number = (
            f"invoice {f.invoice_number.value}"
            if f.invoice_number.value
            else ("an invoice with no invoice number")
        )
        total = (
            f"a total of {_money(f.total.value, f.currency.value)}"
            if f.total.value is not None
            else "no readable total"
        )
        dated = f", dated {f.invoice_date.value.isoformat()}" if f.invoice_date.value else ""
        errors = sum(1 for i in issues if i.severity == "error")
        warnings = sum(1 for i in issues if i.severity == "warning")
        if errors or warnings:
            parts = []
            if errors:
                parts.append(f"{errors} error{'s' if errors != 1 else ''}")
            if warnings:
                parts.append(f"{warnings} warning{'s' if warnings != 1 else ''}")
            outcome = f"The checks raised {' and '.join(parts)} for a person to look at."
        else:
            outcome = "All deterministic checks passed and no field is flagged for review."
        source = " Values were entered by a reviewer." if manual else ""
        reviewed = (
            f" A person marked it reviewed on {doc.reviewed_at.date().isoformat()}."
            if doc.status == "reviewed" and doc.reviewed_at
            else ""
        )
        return f"This is {number} from {vendor} with {total}{dated}. {outcome}{source}{reviewed}"

    # ------------------------------------------------------------------ facts

    @staticmethod
    def _extracted_section(f: InvoiceFields, currency, no_text: bool, manual: bool):
        items: list[ExplanationItem] = []
        if no_text and not manual:
            return ExplanationSection(title="What was extracted", items=items)
        for name in KEY_FIELDS:
            field: ExtractedField = getattr(f, name)
            label = LABELS[name]
            if field.value is not None:
                where = ""
                if field.corrected:
                    where = " (entered by a reviewer)"
                elif field.evidence:
                    where = f" (page {field.evidence.page_number}: “{field.evidence.line}”)"
                items.append(
                    ExplanationItem(
                        kind="fact",
                        text=f"{label}: {_fmt(name, field.value, currency)}{where}.",
                        refs=[name],
                        evidence=[field.evidence] if field.evidence and not field.corrected else [],
                    )
                )
            elif field.status in ("ambiguous", "unparseable"):
                items.append(
                    ExplanationItem(
                        kind="fact",
                        text=f"{label}: printed as “{field.raw}”, which could not be read "
                        "unambiguously, so no value was recorded.",
                        refs=[name],
                        evidence=[field.evidence] if field.evidence else [],
                    )
                )
        if f.line_items:
            items.append(
                ExplanationItem(
                    kind="fact",
                    text=f"{len(f.line_items)} line item{'s' if len(f.line_items) != 1 else ''} "
                    "were read from the item table.",
                    refs=["line_items"],
                )
            )
        return ExplanationSection(title="What was extracted", items=items)

    @staticmethod
    def _checks_section(doc, issues: list[ValidationIssue]):
        items: list[ExplanationItem] = []
        checks = doc.validation.checks
        passed = [c.name.replace("_", " ") for c in checks if c.outcome == "passed"]
        if passed:
            items.append(
                ExplanationItem(
                    kind="fact",
                    text="Passed: " + ", ".join(passed) + ".",
                    refs=[c.name for c in checks if c.outcome == "passed"],
                )
            )
        for issue in issues:
            if issue.severity == "info":
                continue
            items.append(
                ExplanationItem(
                    kind="fact",
                    text=f"{issue.severity.capitalize()}: {issue.message}",
                    refs=[issue.code] + ([issue.field] if issue.field else []),
                )
            )
        return ExplanationSection(title="What the checks found", items=items)

    # ------------------------------------------------------------------ interpretation

    @staticmethod
    def _interpretations(f: InvoiceFields, issues, currency) -> list[ExplanationItem]:
        out: list[ExplanationItem] = []
        seen: set[str] = set()

        def add(code: str, text: str) -> None:
            out.append(ExplanationItem(kind="interpretation", text=text, refs=[code]))

        for issue in issues:
            code = issue.code
            if code == "total_mismatch":
                add(
                    code,
                    f"The printed total ({_money(issue.details.get('printed'), currency)}) and "
                    f"the computed total ({_money(issue.details.get('expected'), currency)}) "
                    "disagree. This could be a typing error on the invoice, transposed digits, "
                    "or a charge that is not itemised. Compare both figures with the original.",
                )
            elif code == "subtotal_mismatch":
                add(
                    code,
                    "The line amounts do not add up to the printed subtotal. A line may be "
                    "missing from the extraction, or the invoice itself may contain an error.",
                )
            elif code == "line_item_amount_mismatch" and code not in seen:
                add(
                    code,
                    "At least one line amount is not quantity × unit price. The vendor may have "
                    "applied an unlisted adjustment, or the line may simply be wrong.",
                )
            elif code == "possible_duplicate":
                d = issue.details
                why = (
                    "is the same file as"
                    if d.get("reason") == "identical_file"
                    else "has the same vendor and invoice number as"
                )
                add(
                    code,
                    f"This document {why} '{d.get('original_filename')}'. It may be a "
                    "resubmission, a reminder, or a legitimately separate invoice that reuses a "
                    "number. It is a similarity flag, not evidence of wrongdoing.",
                )
            elif code == "missing_due_date" and f.payment_terms.value:
                add(
                    code,
                    f"The payment terms say “{f.payment_terms.value}”, so the due date "
                    "may be derived from them, but this tool does not calculate due dates. "
                    "Confirm it from the document or the vendor agreement.",
                )
            elif code == "missing_invoice_number":
                add(
                    code,
                    "Without an invoice number the duplicate check cannot match this document "
                    "against earlier ones.",
                )
            elif code == "fields_need_review":
                low = [
                    LABELS.get(n, n).lower()
                    for n, fld in f.scalar_fields().items()
                    if fld.status == "found" and not fld.corrected and fld.confidence < 0.8
                ]
                if low:
                    add(
                        code,
                        "These values were read with lower confidence (from layout position or "
                        f"OCR) and may be wrong even if they look plausible: {', '.join(low)}.",
                    )
            elif code == "ocr_text":
                add(code, "Text read by OCR can contain character errors such as 0/O or 1/l.")
            seen.add(code)
        if (
            f.currency.value
            and f.currency.status == "found"
            and not f.currency.corrected
            and f.currency.confidence < 0.8
        ):
            out.append(
                ExplanationItem(
                    kind="interpretation",
                    text=f"The currency {f.currency.value} was inferred from a symbol, not a "
                    "printed code.",
                    refs=["currency"],
                )
            )
        return out

    # ------------------------------------------------------------------ questions

    @staticmethod
    def _questions(f: InvoiceFields, issues) -> list[ExplanationItem]:
        qs: list[ExplanationItem] = []
        for name in ("invoice_date", "due_date"):
            field: ExtractedField = getattr(f, name)
            if field.status == "ambiguous" and not field.corrected:
                issue = next(
                    (i for i in issues if i.code == "ambiguous_date" and i.field == name), None
                )
                options = re.findall(r"\d{4}-\d{2}-\d{2}", field.note or "")
                choice = f" Is it {' or '.join(options)}?" if options else " What is the date?"
                qs.append(
                    ExplanationItem(
                        kind="question",
                        text=f"The {LABELS[name].lower()} is printed as “{field.raw}”." + choice,
                        refs=[name] + (["ambiguous_date"] if issue else []),
                        evidence=[field.evidence] if field.evidence else [],
                    )
                )
        codes = {i.code for i in issues}
        if "missing_invoice_number" in codes:
            qs.append(
                ExplanationItem(
                    kind="question",
                    text="Does the original show an invoice number anywhere else, such as a "
                    "header, footer or reference line?",
                    refs=["invoice_number"],
                )
            )
        for issue in issues:
            if issue.code == "possible_duplicate":
                qs.append(
                    ExplanationItem(
                        kind="question",
                        text=f"Was '{issue.details.get('original_filename')}' already processed? "
                        "If so, is this a separate invoice or the same one sent again?",
                        refs=["possible_duplicate"],
                    )
                )
        if (
            f.currency.status == "found"
            and not f.currency.corrected
            and f.currency.confidence < 0.8
        ):
            qs.append(
                ExplanationItem(
                    kind="question",
                    text="Which currency does this invoice use? Only a symbol was printed.",
                    refs=["currency"],
                )
            )
        if "no_line_items" in codes:
            qs.append(
                ExplanationItem(
                    kind="question",
                    text="Does the invoice list individual items? None could be read.",
                    refs=["line_items"],
                )
            )
        return qs

    # ------------------------------------------------------------------ next steps

    @staticmethod
    def _next_steps(doc, issues, no_text: bool, manual: bool) -> list[str]:
        if doc.status == "reviewed":
            return ["No action needed here; reopen the document if something must change."]
        steps: list[str] = []
        if no_text and not manual:
            steps.append("Install Tesseract OCR and re-run extraction, or enter the key fields.")
        codes = {i.code for i in issues}
        if codes & {"total_mismatch", "subtotal_mismatch", "line_item_amount_mismatch"}:
            steps.append("Compare the amounts with the original document.")
        if codes & {"ambiguous_date", "unparseable_date", "missing_due_date"}:
            steps.append("Confirm the dates from the original and correct them if needed.")
        if "possible_duplicate" in codes:
            steps.append("Check the earlier document before deciding how to treat this one.")
        if "fields_need_review" in codes:
            steps.append("Check the highlighted low-confidence fields.")
        steps.append("Correct any wrong values, then mark the document as reviewed.")
        return steps
