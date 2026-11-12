import logging

import pytest

from app.extraction.pdf import PyMuPDFExtractor
from app.repositories.documents import DocumentRepository
from tests.conftest import make_pdf, make_png, upload

TEXT = "SYNTHETIC test invoice INV-0001 from a fictional vendor"


def upload_and_process(client, name, data, ct="application/pdf"):
    doc_id = upload(client, name, data, ct).json()["document_id"]
    r = client.post(f"/api/documents/{doc_id}/process")
    assert r.status_code == 200
    return r.json()


def test_text_pdf_is_extracted_with_page_numbers(client):
    body = upload_and_process(
        client, "inv.pdf", make_pdf(TEXT, "Second page with enough text here")
    )
    assert body["status"] == "extracted"
    assert body["extraction_method"] == "text"
    ex = body["extraction"]
    assert ex["page_count"] == 2
    assert [p["page_number"] for p in ex["pages"]] == [1, 2]
    assert "INV-0001" in ex["pages"][0]["text"]
    assert ex["pages"][1]["method"] == "text"
    assert ex["ocr_available"] is False


def test_blank_pdf_needs_ocr(client):
    body = upload_and_process(client, "blank.pdf", make_pdf(""))
    assert body["status"] == "needs_ocr"
    assert body["extraction_method"] == "none"
    assert any("OCR is not available" in w for w in body["extraction"]["warnings"])


def test_image_upload_needs_ocr_without_tesseract(client):
    body = upload_and_process(client, "scan.png", make_png(), "image/png")
    assert body["status"] == "needs_ocr"
    assert body["extraction"]["pages"][0]["has_images"] is True


def test_missing_stored_file_marks_failed(client, settings):
    doc_id = upload(client, "inv.pdf", make_pdf(TEXT)).json()["document_id"]
    (settings.upload_dir / f"{doc_id}.pdf").unlink()
    r = client.post(f"/api/documents/{doc_id}/process")
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert r.json()["error"] == "Stored file is missing."


def test_detail_and_list(client):
    a = upload(client, "a.pdf", make_pdf(TEXT)).json()["document_id"]
    b = upload(client, "b.pdf", make_pdf(TEXT)).json()["document_id"]
    listed = client.get("/api/documents").json()
    assert [d["document_id"] for d in listed] == [b, a]
    detail = client.get(f"/api/documents/{a}").json()
    assert detail["status"] == "uploaded"
    assert detail["extraction"] is None


@pytest.mark.parametrize("bad_id", ["nope", "../../etc", "A" * 32])
def test_invalid_document_id(client, bad_id):
    assert client.get(f"/api/documents/{bad_id}").status_code in (404, 422)
    assert client.post(f"/api/documents/{bad_id}/process").status_code in (404, 405, 422)


def test_unknown_document_404(client):
    missing = "0" * 32
    assert client.get(f"/api/documents/{missing}").status_code == 404
    assert client.post(f"/api/documents/{missing}/process").status_code == 404


def test_reviewed_document_cannot_be_reprocessed(client, settings):
    doc_id = upload(client, "inv.pdf", make_pdf(TEXT)).json()["document_id"]
    assert client.post(f"/api/documents/{doc_id}/process").status_code == 200
    assert client.post(f"/api/documents/{doc_id}/process").status_code == 200  # re-run ok
    DocumentRepository(settings.database_path).set_status(doc_id, "reviewed")
    assert client.post(f"/api/documents/{doc_id}/process").status_code == 409


def test_logs_do_not_contain_document_text(client, caplog):
    caplog.set_level(logging.DEBUG)
    upload_and_process(client, "inv.pdf", make_pdf(TEXT))
    assert "INV-0001" not in caplog.text


# ----- extractor unit tests with a fake OCR engine -----


class FakeOcr:
    name = "fake-ocr"

    def __init__(self, text="OCR RECOGNISED TEXT FOR THIS PAGE", fail=False):
        self.text, self.fail = text, fail

    def page_text(self, page):
        if self.fail:
            raise RuntimeError("boom")
        return self.text


def write(tmp_path, data, name="doc.pdf"):
    p = tmp_path / name
    p.write_bytes(data)
    return p


def test_ocr_used_only_for_pages_without_text(tmp_path):
    path = write(tmp_path, make_pdf(TEXT, ""))
    result = PyMuPDFExtractor(ocr=FakeOcr()).extract_text(path)
    assert [p.method for p in result.pages] == ["text", "ocr"]
    assert result.method == "mixed"
    assert any("OCR and may contain errors" in w for w in result.warnings)


def test_ocr_failure_is_a_warning_not_a_crash(tmp_path):
    path = write(tmp_path, make_pdf(""))
    result = PyMuPDFExtractor(ocr=FakeOcr(fail=True)).extract_text(path)
    assert result.method == "none"
    assert any("OCR failed" in w for w in result.warnings)


def test_ocr_with_too_little_text_is_none(tmp_path):
    path = write(tmp_path, make_pdf(""))
    result = PyMuPDFExtractor(ocr=FakeOcr(text="~")).extract_text(path)
    assert result.method == "none"
