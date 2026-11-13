"""Corrections, review status and original-file access."""

from pathlib import Path

import pytest

from tests.conftest import make_pdf, upload

SAMPLES = Path(__file__).resolve().parent.parent / "sample_data" / "invoices"


def processed(client, name: str) -> dict:
    data = (SAMPLES / f"{name}.pdf").read_bytes()
    doc_id = upload(client, f"{name}.pdf", data).json()["document_id"]
    return client.post(f"/api/documents/{doc_id}/process").json()


def correct(client, doc_id, *items):
    body = {"corrections": [dict(zip(("field", "value", "note"), i, strict=False)) for i in items]}
    return client.post(f"/api/documents/{doc_id}/corrections", json=body)


def codes(detail):
    return {i["code"] for i in detail["validation"]["issues"]}


def test_correcting_ambiguous_date_keeps_original_and_clears_issue(client):
    doc = processed(client, "inv13_ambiguous_date")
    assert doc["status"] == "needs_review"

    r = correct(client, doc["document_id"], ("invoice_date", "2026-04-05", "Confirmed with vendor"))
    assert r.status_code == 200
    d = r.json()
    # Extracted field untouched
    assert d["fields"]["invoice_date"]["status"] == "ambiguous"
    assert d["fields"]["invoice_date"]["value"] is None
    # Audit record
    [c] = d["corrections"]
    assert c["field"] == "invoice_date"
    assert c["original_value"] == "04/05/2026"
    assert c["original_status"] == "ambiguous"
    assert c["corrected_value"] == "2026-04-05"
    assert c["note"] == "Confirmed with vendor"
    # Validation now runs on the corrected value
    assert "ambiguous_date" not in codes(d)
    assert d["validation"]["fields_needing_review"] == []
    assert d["status"] == "processed"


def test_correcting_total_resolves_mismatch_without_touching_extraction(client):
    doc = processed(client, "inv04_arithmetic_mismatch")
    d = correct(client, doc["document_id"], ("total", "736.70")).json()
    assert d["fields"]["total"]["value"] == "763.70"
    assert "total_mismatch" not in codes(d)
    assert d["status"] == "processed"


def test_latest_correction_wins_and_history_is_kept(client):
    doc = processed(client, "inv01_normal")
    doc_id = doc["document_id"]
    correct(client, doc_id, ("payment_terms", "Net 45"))
    d = correct(client, doc_id, ("payment_terms", "Net 30")).json()
    assert [c["corrected_value"] for c in d["corrections"]] == ["Net 45", "Net 30"]
    assert d["status"] == "processed"


def test_clearing_a_required_field_raises_issue(client):
    doc = processed(client, "inv01_normal")
    d = correct(client, doc["document_id"], ("invoice_number", None)).json()
    assert "missing_invoice_number" in codes(d)
    assert d["status"] == "needs_review"


@pytest.mark.parametrize(
    "field, value",
    [
        ("invoice_date", "04/05/2026"),
        ("total", "$1,000.00"),
        ("total", "-5"),
        ("currency", "dollars"),
    ],
)
def test_invalid_corrections_are_rejected(client, field, value):
    doc = processed(client, "inv01_normal")
    r = correct(client, doc["document_id"], (field, value))
    assert r.status_code == 422
    assert r.json()["detail"]["field"] == field
    # Nothing recorded
    assert client.get(f"/api/documents/{doc['document_id']}").json()["corrections"] == []


def test_unknown_or_line_item_fields_cannot_be_corrected(client):
    doc = processed(client, "inv01_normal")
    for field in ("line_items", "status", "payment_approved"):
        assert correct(client, doc["document_id"], (field, "x")).status_code == 422


def test_cannot_correct_before_processing(client):
    doc_id = upload(client, "a.pdf", make_pdf("some synthetic text here")).json()["document_id"]
    assert correct(client, doc_id, ("total", "1.00")).status_code == 409


def test_review_locks_and_reopen_unlocks(client):
    doc = processed(client, "inv04_arithmetic_mismatch")
    doc_id = doc["document_id"]

    r = client.post(f"/api/documents/{doc_id}/review", json={"note": "Checked against PDF"})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "reviewed"
    assert d["reviewed_at"]
    assert d["review_note"] == "Checked against PDF"
    # Reviewing does not change validation findings
    assert "total_mismatch" in codes(d)

    assert correct(client, doc_id, ("total", "736.70")).status_code == 409
    assert client.post(f"/api/documents/{doc_id}/process").status_code == 409

    r = client.post(f"/api/documents/{doc_id}/review", json={"reviewed": False})
    assert r.status_code == 200
    assert r.json()["status"] == "needs_review"
    assert r.json()["reviewed_at"] is None
    assert (
        client.post(f"/api/documents/{doc_id}/review", json={"reviewed": False}).status_code == 409
    )


def test_cannot_review_unprocessed_document(client):
    doc_id = upload(client, "a.pdf", make_pdf("some synthetic text here")).json()["document_id"]
    assert client.post(f"/api/documents/{doc_id}/review", json={}).status_code == 409


def test_reprocessing_keeps_corrections(client):
    doc = processed(client, "inv13_ambiguous_date")
    doc_id = doc["document_id"]
    correct(client, doc_id, ("invoice_date", "2026-05-04"))
    d = client.post(f"/api/documents/{doc_id}/process").json()
    assert len(d["corrections"]) == 1
    assert d["status"] == "processed"


def test_manual_entry_for_scanned_document(client):
    doc = processed(client, "inv09_scanned")
    assert doc["status"] == "needs_ocr"
    d = correct(
        client,
        doc["document_id"],
        ("vendor_name", "Tidewell Catering Co."),
        ("invoice_number", "TCC-1189"),
        ("invoice_date", "2026-02-14"),
        ("due_date", "2026-02-28"),
        ("currency", "usd"),
        ("total", "765.73"),
    ).json()
    assert "manual_entry" in codes(d)
    assert "ocr_required" not in codes(d)
    assert d["status"] == "needs_review"  # still no line items to check
    assert next(c for c in d["corrections"] if c["field"] == "currency")["corrected_value"] == "USD"


def test_correction_can_reveal_possible_duplicate(client):
    first = processed(client, "inv01_normal")
    second = processed(client, "inv02_missing_invoice_number")
    d = correct(
        client,
        second["document_id"],
        ("vendor_name", "Quillfeather Office Goods"),
        ("invoice_number", "QOG-2026-0142"),
    ).json()
    dup = next(i for i in d["validation"]["issues"] if i["code"] == "possible_duplicate")
    assert dup["details"]["document_id"] == first["document_id"]


def test_original_file_is_served_read_only(client):
    doc = processed(client, "inv01_normal")
    r = client.get(f"/api/documents/{doc['document_id']}/file")
    assert r.status_code == 200
    assert r.content == (SAMPLES / "inv01_normal.pdf").read_bytes()
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("inline;")
    assert client.get(f"/api/documents/{'0' * 32}/file").status_code == 404
