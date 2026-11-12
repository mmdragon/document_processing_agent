MINIMAL_PDF = b"%PDF-1.4\n%synthetic test\n"


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_upload_pdf_stores_under_server_name(client, settings):
    r = client.post(
        "/api/documents",
        files={"file": ("../../etc/invoice.pdf", MINIMAL_PDF, "application/pdf")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["original_filename"] == "invoice.pdf"
    assert body["status"] == "uploaded"
    stored = list(settings.upload_dir.iterdir())
    assert [p.name for p in stored] == [f"{body['document_id']}.pdf"]


def test_rejects_unsupported_extension(client, settings):
    r = client.post("/api/documents", files={"file": ("run.sh", b"#!/bin/sh", "text/plain")})
    assert r.status_code == 415


def test_rejects_mismatched_signature(client, settings):
    r = client.post("/api/documents", files={"file": ("fake.pdf", b"not a pdf", "application/pdf")})
    assert r.status_code == 415
    assert list(settings.upload_dir.iterdir()) == []


def test_rejects_oversized(client, settings):
    big = MINIMAL_PDF + b"0" * 2048
    r = client.post("/api/documents", files={"file": ("big.pdf", big, "application/pdf")})
    assert r.status_code == 413
    assert list(settings.upload_dir.iterdir()) == []


def test_rejects_empty(client, settings):
    r = client.post("/api/documents", files={"file": ("empty.pdf", b"", "application/pdf")})
    assert r.status_code == 400
