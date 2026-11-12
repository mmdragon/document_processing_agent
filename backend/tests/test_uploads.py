import pymupdf
import pytest

from app.uploads import safe_display_name
from tests.conftest import make_pdf, make_png, upload

TEXT = "SYNTHETIC test invoice INV-0001 from a fictional vendor"


def stored_files(settings):
    return (
        sorted(p.name for p in settings.upload_dir.iterdir())
        if settings.upload_dir.exists()
        else []
    )


def error_code(r):
    return r.json()["detail"]["code"]


def test_valid_pdf_is_stored_under_server_generated_name(client, settings):
    r = upload(client, "invoice.pdf", make_pdf(TEXT))
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "uploaded"
    assert body["page_count"] == 1
    assert body["content_type"] == "application/pdf"
    assert len(body["sha256"]) == 64
    assert stored_files(settings) == [f"{body['document_id']}.pdf"]


@pytest.mark.parametrize(
    "name, expected",
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("C:\\Users\\x\\invoice.pdf", "invoice.pdf"),
    ],
)
def test_client_paths_are_never_used(client, settings, name, expected):
    r = upload(client, name, make_pdf(TEXT))
    assert r.status_code == 201
    assert r.json()["original_filename"] == expected
    # Nothing written outside the upload directory; only the UUID name inside it.
    assert stored_files(settings) == [f"{r.json()['document_id']}.pdf"]


def test_content_type_comes_from_signature_not_client_header(client):
    r = upload(client, "invoice.pdf", make_pdf(TEXT), content_type="text/html")
    assert r.status_code == 201
    assert r.json()["content_type"] == "application/pdf"


def test_png_accepted(client):
    r = upload(client, "scan.png", make_png(), "image/png")
    assert r.status_code == 201
    assert r.json()["content_type"] == "image/png"


@pytest.mark.parametrize("name", ["run.sh", "invoice.exe", "invoice.html", "invoice", "x.pdf.js"])
def test_rejects_unsupported_types(client, settings, name):
    r = upload(client, name, b"%PDF-1.7 whatever", "application/pdf")
    assert r.status_code == 415
    assert error_code(r) == "unsupported_type"
    assert stored_files(settings) == []


@pytest.mark.parametrize(
    "name, data",
    [("fake.pdf", b"not a pdf at all"), ("fake.png", make_pdf(TEXT)), ("fake.jpg", make_png())],
)
def test_rejects_signature_mismatch(client, settings, name, data):
    r = upload(client, name, data)
    assert r.status_code == 415
    assert error_code(r) == "signature_mismatch"
    assert stored_files(settings) == []


def test_rejects_oversized(client, settings):
    big = b"%PDF-1.7\n" + b"0" * settings.max_upload_bytes
    r = upload(client, "big.pdf", big)
    assert r.status_code == 413
    assert error_code(r) == "file_too_large"
    assert stored_files(settings) == []


def test_rejects_empty_file(client, settings):
    r = upload(client, "empty.pdf", b"")
    assert r.status_code == 400
    assert error_code(r) == "empty_file"
    assert stored_files(settings) == []


def test_rejects_malformed_pdf(client, settings):
    r = upload(client, "broken.pdf", b"%PDF-1.7\n" + b"\x00garbage\xff" * 200)
    assert r.status_code == 422
    assert error_code(r) in {"malformed_file", "no_pages"}
    assert stored_files(settings) == []


def test_rejects_encrypted_pdf(client, settings):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), TEXT)
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="u", owner_pw="o")
    r = upload(client, "locked.pdf", data)
    assert r.status_code == 422
    assert error_code(r) == "encrypted_pdf"
    assert stored_files(settings) == []


def test_rejects_too_many_pages(client, settings):
    r = upload(client, "long.pdf", make_pdf(*(["page"] * (settings.max_pages + 1))))
    assert r.status_code == 422
    assert error_code(r) == "too_many_pages"
    assert stored_files(settings) == []


def test_rejected_uploads_are_not_recorded(client):
    upload(client, "empty.pdf", b"")
    upload(client, "run.sh", b"#!/bin/sh")
    assert client.get("/api/documents").json() == []


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("in\x00vo\nice.pdf", "invoice.pdf"),
        ("../../x/../evil.pdf", "evil.pdf"),
        ("", "unnamed"),
        (None, "unnamed"),
        ("a" * 400 + ".pdf", "a" * 251 + ".pdf"),
    ],
)
def test_safe_display_name(raw, expected):
    assert safe_display_name(raw) == expected
