"""Review report: corrected field values with their source, checks, corrections and the
explainer summary, as JSON or Markdown."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.agents.mock import LABELS
from app.agents.models import DISCLAIMER, Explanation
from app.review import apply_corrections
from app.schemas.documents import Correction, DocumentDetail, DocumentSummary
from app.schemas.invoice import Evidence, LineItem, ValidationCheck, ValidationIssue

SYNTHETIC_NOTICE = "Generated from synthetic test data by a local review tool."


class ReportField(BaseModel):
    field: str
    label: str
    value: str | None
    source: Literal["extracted", "corrected", "missing", "unresolved"]
    extracted_value: str | None = None  # shown when a reviewer changed the value
    evidence: Evidence | None = None


class ReviewReport(BaseModel):
    title: str
    generated_at: datetime
    notice: str = SYNTHETIC_NOTICE
    disclaimer: str = DISCLAIMER
    document: DocumentSummary
    review_note: str | None
    fields: list[ReportField]
    line_items: list[LineItem]
    issues: list[ValidationIssue]
    checks: list[ValidationCheck]
    corrections: list[Correction]
    explanation: Explanation


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def build_report(detail: DocumentDetail, explanation: Explanation) -> ReviewReport:
    assert detail.fields is not None and detail.validation is not None
    effective = apply_corrections(detail.fields, detail.corrections)
    rows: list[ReportField] = []
    for name, eff in effective.scalar_fields().items():
        original = getattr(detail.fields, name)
        if eff.corrected:
            source = "corrected"
        elif eff.status == "found":
            source = "extracted"
        elif eff.status == "missing":
            source = "missing"
        else:
            source = "unresolved"
        rows.append(
            ReportField(
                field=name,
                label=LABELS.get(name, name),
                value=_text(eff.value)
                if eff.value is not None
                else (eff.raw if source == "unresolved" else None),
                source=source,
                extracted_value=(_text(original.value) or original.raw) if eff.corrected else None,
                evidence=original.evidence,
            )
        )
    summary = DocumentSummary.model_validate(
        detail.model_dump(include=set(DocumentSummary.model_fields))
    )
    return ReviewReport(
        title=f"Invoice review: {detail.original_filename}",
        generated_at=datetime.now(UTC),
        document=summary,
        review_note=detail.review_note,
        fields=rows,
        line_items=effective.line_items,
        issues=detail.validation.issues,
        checks=detail.validation.checks,
        corrections=detail.corrections,
        explanation=explanation,
    )


def _cell(text: str | None) -> str:
    return (text or "—").replace("|", "\\|").replace("\n", " ")


def to_markdown(r: ReviewReport) -> str:
    d = r.document
    kind = "model-generated" if r.explanation.model_generated else "deterministic, not a model"
    out = [
        f"# {r.title}",
        "",
        f"> {r.notice} {r.disclaimer}",
        "",
        f"- **Status:** {d.status}",
        f"- **Uploaded:** {d.uploaded_at.isoformat(timespec='seconds')}",
        f"- **Pages:** {d.page_count} · **Text from:** {d.extraction_method or '—'}",
        f"- **SHA-256:** `{d.sha256}`",
    ]
    if d.reviewed_at:
        out.append(f"- **Reviewed:** {d.reviewed_at.isoformat(timespec='seconds')}")
    if r.review_note:
        out.append(f"- **Review note:** {r.review_note}")
    out += [
        f"- **Report generated:** {r.generated_at.isoformat(timespec='seconds')}",
        "",
        "## Summary",
        "",
        f"_Written by the {r.explanation.explainer} explainer ({kind})._",
        "",
        r.explanation.summary,
        "",
        "## Fields",
        "",
        "| Field | Value | Source | Evidence |",
        "|---|---|---|---|",
    ]
    for f in r.fields:
        source = f.source
        if f.source == "corrected":
            source = f"corrected (extracted: {_cell(f.extracted_value)})"
        ev = f"p.{f.evidence.page_number}: `{_cell(f.evidence.line)}`" if f.evidence else "—"
        out.append(f"| {f.label} | {_cell(f.value)} | {source} | {ev} |")

    out += ["", "## Line items", ""]
    if r.line_items:
        out += ["| Description | Qty | Unit price | Amount |", "|---|---:|---:|---:|"]
        for li in r.line_items:
            out.append(
                f"| {_cell(li.description)} | {li.quantity} | {li.unit_price} | {li.amount} |"
            )
    else:
        out.append("No line items were read.")

    out += ["", "## Issues", ""]
    if r.issues:
        for i in r.issues:
            out.append(f"- **{i.severity}** `{i.code}`: {i.message}")
    else:
        out.append("No issues found.")

    out += ["", "## Checks", ""]
    for c in r.checks:
        out.append(f"- **{c.outcome}** {c.name.replace('_', ' ')}: {c.detail}")

    if r.corrections:
        out += ["", "## Corrections", ""]
        for c in r.corrections:
            note = f" ({c.note})" if c.note else ""
            out.append(
                f"- {c.corrected_at.isoformat(timespec='seconds')} · {c.field}: "
                f"{c.original_value or '—'} → {c.corrected_value or '(cleared)'}{note}"
            )

    interp = [i for s in r.explanation.sections for i in s.items if i.kind == "interpretation"]
    if interp or r.explanation.questions:
        out += ["", "## Interpretation and open questions", ""]
        out += [f"- _Interpretation:_ {i.text}" for i in interp]
        out += [f"- _Question:_ {q.text}" for q in r.explanation.questions]

    out += ["", "## Next steps", ""] + [f"- {s}" for s in r.explanation.next_steps]
    out += ["", "---", "", r.disclaimer, ""]
    return "\n".join(out)
