"""Checks on the synthetic dataset itself (not on the extraction pipeline)."""

import json
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest

from app.schemas.ground_truth import GroundTruth

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"
PDFS = sorted((SAMPLE / "invoices").glob("*.pdf"))
GTS = sorted((SAMPLE / "ground_truth").glob("*.json"))
REQUIRED_SCENARIOS = {
    "normal",
    "missing_invoice_number",
    "missing_due_date",
    "arithmetic_mismatch",
    "duplicate",
    "multiple_line_items",
    "discount",
    "tax_and_shipping",
    "scanned_image",
    "unusual_date_format",
    "low_quality_ocr",
    "non_usd_currency",
}


def load(path: Path) -> GroundTruth:
    return GroundTruth.model_validate(json.loads(path.read_text()))


def test_dataset_size_and_pairing():
    assert len(PDFS) >= 12
    assert {p.stem for p in PDFS} == {g.stem for g in GTS}


def test_required_scenarios_present():
    assert REQUIRED_SCENARIOS <= {load(g).scenario for g in GTS}


@pytest.mark.parametrize("gt_path", GTS, ids=lambda p: p.stem)
def test_ground_truth_consistent_with_expected_issues(gt_path):
    gt = load(gt_path)
    f = gt.fields
    issues = set(gt.expected_issues)
    assert gt.file_name == f"{gt_path.stem}.pdf"

    line_ok = all(
        li.amount == (li.quantity * li.unit_price).quantize(Decimal("0.01")) for li in f.line_items
    )
    assert line_ok == ("line_item_amount_mismatch" not in issues)

    assert (f.subtotal == sum(li.amount for li in f.line_items)) == (
        "subtotal_mismatch" not in issues
    )

    expected_total = f.subtotal - (f.discount or 0) + (f.tax or 0) + (f.shipping or 0)
    assert (f.total == expected_total) == ("total_mismatch" not in issues)

    assert (f.invoice_number is None) == ("missing_invoice_number" in issues)
    assert (f.due_date_raw is None) == ("missing_due_date" in issues)
    if "ambiguous_date" in issues:
        assert f.invoice_date is None and f.invoice_date_raw
    assert ("ocr_required" in issues) == (gt.expected_extraction_method == "ocr")


def test_duplicate_points_at_matching_invoice():
    by_id = {g.stem: load(g) for g in GTS}
    dups = [gt for gt in by_id.values() if gt.duplicate_of]
    assert dups
    for gt in dups:
        original = by_id[gt.duplicate_of]
        assert gt.fields.vendor_name == original.fields.vendor_name
        assert gt.fields.invoice_number == original.fields.invoice_number


@pytest.mark.parametrize("pdf_path", PDFS, ids=lambda p: p.stem)
def test_pdf_is_marked_synthetic_and_matches_render_mode(pdf_path):
    gt = load(SAMPLE / "ground_truth" / f"{pdf_path.stem}.json")
    with pymupdf.open(pdf_path) as doc:
        assert "SYNTHETIC" in (doc.metadata.get("title") or "")
        text = "".join(page.get_text() for page in doc)
    if gt.expected_extraction_method == "text":
        assert "SYNTHETIC SAMPLE" in text
        assert gt.fields.vendor_name in text
        if gt.fields.invoice_number:
            assert gt.fields.invoice_number in text
    else:
        assert text.strip() == "", "scanned samples must have no text layer"
