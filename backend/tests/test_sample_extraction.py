"""Run upload + extraction on every synthetic sample invoice."""

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


@pytest.mark.parametrize("gt", CASES, ids=lambda g: g.document_id)
def test_sample_upload_and_extract(client, gt):
    data = (SAMPLE / "invoices" / gt.file_name).read_bytes()
    doc_id = upload(client, gt.file_name, data).json()["document_id"]
    body = client.post(f"/api/documents/{doc_id}/process").json()

    if gt.expected_extraction_method == "text":
        assert body["status"] == "extracted"
        assert body["extraction_method"] == "text"
        text = body["extraction"]["pages"][0]["text"]
        assert gt.fields.vendor_name in text
        if gt.fields.invoice_number:
            assert gt.fields.invoice_number in text
        if gt.fields.invoice_date_raw:
            assert gt.fields.invoice_date_raw in text
    else:
        # OCR is disabled in tests by default.
        assert body["status"] == "needs_ocr"
        assert body["extraction_method"] == "none"


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed")
def test_clean_scan_with_real_tesseract():
    path = SAMPLE / "invoices" / "inv09_scanned.pdf"
    result = PyMuPDFExtractor(ocr=TesseractOcr()).extract_text(path)
    assert result.method == "ocr"
    assert "Tidewell" in result.pages[0].text
