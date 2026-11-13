"""End-to-end: upload + process every synthetic invoice and compare with ground truth."""

import json
import shutil
from pathlib import Path

import pytest

from app.extraction.ocr import TesseractOcr
from app.extraction.pdf import PyMuPDFExtractor
from app.schemas.ground_truth import GroundTruth
from tests.conftest import upload

SAMPLE = Path(__file__).resolve().parent.parent / "sample_data"
CASES = [
    GroundTruth.model_validate(json.loads(p.read_text()))
    for p in sorted((SAMPLE / "ground_truth").glob("*.json"))
]
TEXT_CASES = [c for c in CASES if c.expected_extraction_method == "text"]
SCAN_CASES = [c for c in CASES if c.expected_extraction_method == "ocr"]
# Issue codes the ground truth knows about; other codes (e.g. fields_need_review) are
# compared separately.
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


def process_sample(client, gt: GroundTruth) -> dict:
    data = (SAMPLE / "invoices" / gt.file_name).read_bytes()
    doc_id = upload(client, gt.file_name, data).json()["document_id"]
    r = client.post(f"/api/documents/{doc_id}/process")
    assert r.status_code == 200
    return r.json()


def value(fields: dict, name: str):
    return fields[name]["value"]


@pytest.mark.parametrize("gt", TEXT_CASES, ids=lambda g: g.document_id)
def test_fields_match_ground_truth(client, gt):
    body = process_sample(client, gt)
    f = body["fields"]
    t = gt.fields

    assert value(f, "vendor_name") == t.vendor_name
    assert value(f, "vendor_address") == t.vendor_address
    assert value(f, "invoice_number") == t.invoice_number
    assert value(f, "invoice_date") == (t.invoice_date.isoformat() if t.invoice_date else None)
    assert f["invoice_date"]["raw"] == t.invoice_date_raw
    assert value(f, "due_date") == (t.due_date.isoformat() if t.due_date else None)
    assert value(f, "currency") == t.currency
    assert value(f, "purchase_order_number") == t.purchase_order_number
    assert value(f, "payment_terms") == t.payment_terms
    for name in ("subtotal", "discount", "tax", "shipping", "total"):
        expected = getattr(t, name)
        got = value(f, name)
        assert (None if got is None else str(got)) == (
            None if expected is None else str(expected)
        ), name

    items = [
        (i["description"], str(i["quantity"]), str(i["unit_price"]), str(i["amount"]))
        for i in f["line_items"]
    ]
    expected_items = [
        (i.description, str(i.quantity), str(i.unit_price), str(i.amount)) for i in t.line_items
    ]
    assert items == expected_items
    assert f["extraction_notes"] == []

    # Every found field points back at the page/line it came from.
    for field in f.values():
        if isinstance(field, dict) and field.get("status") == "found":
            assert field["evidence"]["page_number"] == 1
            assert (
                field["raw"]
                and field["raw"].split("\n")[0] in body["extraction"]["pages"][0]["text"]
            )


@pytest.mark.parametrize("gt", TEXT_CASES, ids=lambda g: g.document_id)
def test_issues_match_ground_truth(client, gt):
    """No missed issues and no false positives (duplicates are tested separately)."""
    body = process_sample(client, gt)
    codes = {i["code"] for i in body["validation"]["issues"]}
    expected = set(gt.expected_issues) - {"possible_duplicate"}
    assert codes & GT_CODES == expected

    clean = not expected
    assert body["status"] == ("processed" if clean else "needs_review")
    if clean:
        assert body["validation"]["fields_needing_review"] == []
        assert all(c["outcome"] != "failed" for c in body["validation"]["checks"])


@pytest.mark.parametrize("gt", SCAN_CASES, ids=lambda g: g.document_id)
def test_scans_need_ocr(client, gt):
    body = process_sample(client, gt)  # OCR disabled in tests
    assert body["status"] == "needs_ocr"
    assert body["extraction_method"] == "none"
    assert [i["code"] for i in body["validation"]["issues"]] == ["ocr_required"]


def test_duplicate_flagged_as_possible_only(client):
    by_id = {c.document_id: c for c in CASES}
    first = process_sample(client, by_id["inv01_normal"])
    assert first["status"] == "processed"

    second = process_sample(client, by_id["inv05_duplicate"])
    dups = [i for i in second["validation"]["issues"] if i["code"] == "possible_duplicate"]
    assert len(dups) == 1
    assert dups[0]["details"]["document_id"] == first["document_id"]
    assert dups[0]["details"]["reason"] == "same_vendor_and_number"
    assert dups[0]["severity"] == "warning"
    assert "Possible duplicate" in dups[0]["message"]
    assert "not a finding of fraud" in dups[0]["message"]
    assert second["status"] == "needs_review"


def test_identical_file_flagged(client):
    gt = next(c for c in CASES if c.document_id == "inv07_discount")
    process_sample(client, gt)
    again = process_sample(client, gt)
    reasons = [
        i["details"]["reason"]
        for i in again["validation"]["issues"]
        if i["code"] == "possible_duplicate"
    ]
    assert reasons == ["same_vendor_and_number"]  # same key wins; one entry per document


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_clean_scan_with_real_tesseract():
    path = SAMPLE / "invoices" / "inv09_scanned.pdf"
    result = PyMuPDFExtractor(ocr=TesseractOcr()).extract_text(path)
    assert result.method == "ocr"
    assert "Tidewell" in result.pages[0].text
