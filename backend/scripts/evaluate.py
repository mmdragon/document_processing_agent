"""Score the extraction + validation pipeline against the ground-truth JSON.

Runs the same code the API uses (text extraction -> field extraction -> validation,
with duplicate detection across the samples in file order) without a database or
server, then compares every field and every expected issue.

Usage (from backend/):
    uv run python scripts/evaluate.py                # Markdown report to stdout
    uv run python scripts/evaluate.py --json out.json
    uv run python scripts/evaluate.py --ocr          # use Tesseract if installed

Exit code is 1 if any text-layer invoice has a wrong field, a missed issue or a
false-positive issue, so it can gate CI.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.extraction.fields import RuleBasedFieldExtractor  # noqa: E402
from app.extraction.ocr import get_ocr_engine  # noqa: E402
from app.extraction.pdf import PyMuPDFExtractor  # noqa: E402
from app.normalization.parsers import invoice_number_key, vendor_key  # noqa: E402
from app.schemas.ground_truth import GroundTruth  # noqa: E402
from app.schemas.invoice import DuplicateCandidate  # noqa: E402
from app.validation.invoice import InvoiceValidator  # noqa: E402

SAMPLES = BACKEND_ROOT / "sample_data"
SCALARS = (
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
)
GT_CODES = {
    "missing_invoice_number",
    "missing_due_date",
    "line_item_amount_mismatch",
    "subtotal_mismatch",
    "total_mismatch",
    "possible_duplicate",
    "ambiguous_date",
    "ocr_required",
    "low_quality_scan",
}


def _norm(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return f"{v:.2f}" if v == v.quantize(Decimal("0.01")) else str(v.normalize())
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


@dataclass
class FieldResult:
    field: str
    expected: str | None
    got: str | None
    outcome: str  # correct | wrong | missed | spurious


@dataclass
class DocResult:
    document_id: str
    scenario: str
    method: str
    fields: list[FieldResult]
    line_items_correct: bool
    expected_issues: list[str]
    found_issues: list[str]
    missed_issues: list[str] = field(default_factory=list)
    false_issues: list[str] = field(default_factory=list)

    @property
    def fields_correct(self) -> int:
        return sum(f.outcome == "correct" for f in self.fields)


def _compare(expected, got) -> str:
    e, g = _norm(expected), _norm(got)
    if e == g:
        return "correct"
    if g is None:
        return "missed"
    if e is None:
        return "spurious"
    return "wrong"


def evaluate(use_ocr: bool = False) -> list[DocResult]:
    extractor = PyMuPDFExtractor(ocr=get_ocr_engine(use_ocr, "eng"))
    fields_x = RuleBasedFieldExtractor()
    validator = InvoiceValidator()
    seen: list[tuple[str, str, str]] = []  # (doc_id, vendor_key, invoice_key)
    results: list[DocResult] = []

    for gt_path in sorted((SAMPLES / "ground_truth").glob("*.json")):
        gt = GroundTruth.model_validate(json.loads(gt_path.read_text()))
        extraction = extractor.extract_text(SAMPLES / "invoices" / gt.file_name)
        f = fields_x.extract_fields(extraction)

        v_key = vendor_key(f.vendor_name.value)
        i_key = invoice_number_key(f.invoice_number.value)
        dups = [
            DuplicateCandidate(
                reason="same_vendor_and_number",
                document_id=doc_id,
                original_filename=f"{doc_id}.pdf",
                uploaded_at="1970-01-01T00:00:00+00:00",
                vendor_name=None,
                invoice_number=None,
                sha256="",
            )
            for doc_id, vk, ik in seen
            if v_key and i_key and (vk, ik) == (v_key, i_key)
        ]
        if v_key and i_key:
            seen.append((gt.document_id, v_key, i_key))
        validation = validator.validate(f, extraction_method=extraction.method, duplicates=dups)

        t = gt.fields
        field_results = [
            FieldResult(
                name,
                _norm(getattr(t, name)),
                _norm(getattr(f, name).value),
                _compare(getattr(t, name), getattr(f, name).value),
            )
            for name in SCALARS
        ]
        got_items = [
            (i.description, _norm(i.quantity), _norm(i.unit_price), _norm(i.amount))
            for i in f.line_items
        ]
        exp_items = [
            (i.description, _norm(i.quantity), _norm(i.unit_price), _norm(i.amount))
            for i in t.line_items
        ]
        found = sorted({i.code for i in validation.issues} & GT_CODES)
        expected = sorted(gt.expected_issues)
        results.append(
            DocResult(
                document_id=gt.document_id,
                scenario=gt.scenario,
                method=extraction.method,
                fields=field_results,
                line_items_correct=got_items == exp_items,
                expected_issues=expected,
                found_issues=found,
                missed_issues=sorted(set(expected) - set(found)),
                false_issues=sorted(set(found) - set(expected)),
            )
        )
    return results


def to_markdown(results: list[DocResult]) -> str:
    text_docs = [r for r in results if r.method != "none"]
    no_text = [r for r in results if r.method == "none"]
    out = ["# Ground-truth evaluation", ""]

    def pct(a: int, b: int) -> str:
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "—"

    tf = sum(r.fields_correct for r in text_docs)
    tt = sum(len(r.fields) for r in text_docs)
    af = sum(r.fields_correct for r in results)
    at = sum(len(r.fields) for r in results)
    out += [
        "| Scope | Documents | Fields correct | Line-item tables exact "
        "| Issues: missed | Issues: false |",
        "|---|---:|---:|---:|---:|---:|",
        f"| Text-layer PDFs | {len(text_docs)} | {pct(tf, tt)} | "
        f"{pct(sum(r.line_items_correct for r in text_docs), len(text_docs))} | "
        f"{sum(len(r.missed_issues) for r in text_docs)} | "
        f"{sum(len(r.false_issues) for r in text_docs)} |",
        f"| All samples | {len(results)} | {pct(af, at)} | "
        f"{pct(sum(r.line_items_correct for r in results), len(results))} | "
        f"{sum(len(r.missed_issues) for r in results)} | "
        f"{sum(len(r.false_issues) for r in results)} |",
        "",
    ]
    if no_text:
        out += [
            f"{len(no_text)} sample(s) had no text layer and no OCR, so none of their fields "
            "could be read: " + ", ".join(r.document_id for r in no_text) + ".",
            "",
        ]

    out += ["## Per field (text-layer PDFs)", "", "| Field | Correct |", "|---|---:|"]
    for name in SCALARS:
        ok = sum(
            1 for r in text_docs for f in r.fields if f.field == name and f.outcome == "correct"
        )
        out.append(f"| {name} | {pct(ok, len(text_docs))} |")

    out += [
        "",
        "## Per document",
        "",
        "| Document | Text from | Fields | Line items | Expected issues | Missed | False |",
        "|---|---|---:|---|---|---|---|",
    ]
    for r in results:
        out.append(
            f"| {r.document_id} | {r.method} | {r.fields_correct}/{len(r.fields)} | "
            f"{'exact' if r.line_items_correct else 'differs'} | "
            f"{', '.join(r.expected_issues) or '—'} | {', '.join(r.missed_issues) or '—'} | "
            f"{', '.join(r.false_issues) or '—'} |"
        )

    wrong = [(r.document_id, f) for r in results for f in r.fields if f.outcome != "correct"]
    if wrong:
        out += ["", "## Field differences", ""]
        for doc_id, f in wrong:
            out.append(
                f"- {doc_id} · {f.field}: expected {f.expected!r}, got {f.got!r} ({f.outcome})"
            )
    return "\n".join(out) + "\n"


def text_layer_failures(results: list[DocResult]) -> int:
    return sum(
        (len(r.fields) - r.fields_correct)
        + (not r.line_items_correct)
        + len(r.missed_issues)
        + len(r.false_issues)
        for r in results
        if r.method != "none"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, help="also write detailed results as JSON")
    parser.add_argument("--ocr", action="store_true", help="use Tesseract OCR if installed")
    args = parser.parse_args(argv)

    results = evaluate(use_ocr=args.ocr)
    print(to_markdown(results), end="")
    if args.json:
        payload = [asdict(r) | {"fields_correct": r.fields_correct} for r in results]
        args.json.write_text(json.dumps(payload, indent=2) + "\n")
    return 1 if text_layer_failures(results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
