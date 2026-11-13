import sqlite3

from app.repositories.documents import DocumentRepository

PHASE3_SCHEMA = """
CREATE TABLE documents (
    id TEXT PRIMARY KEY, original_filename TEXT NOT NULL, stored_filename TEXT NOT NULL,
    content_type TEXT NOT NULL, size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL,
    page_count INTEGER NOT NULL, uploaded_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    status TEXT NOT NULL, extraction_method TEXT, error TEXT, extraction_json TEXT
);
INSERT INTO documents VALUES ('a', 'old.pdf', 'a.pdf', 'application/pdf', 10, 'x', 1,
    '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', 'uploaded', NULL, NULL, NULL);
"""


def test_phase3_database_is_upgraded_in_place(tmp_path):
    db = tmp_path / "old.sqlite3"
    with sqlite3.connect(db) as conn:
        conn.executescript(PHASE3_SCHEMA)
    repo = DocumentRepository(db)
    detail = repo.get_detail("a")
    assert detail is not None
    assert detail.original_filename == "old.pdf"
    assert detail.fields is None and detail.validation is None
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)")}
    assert {"fields_json", "validation_json", "vendor_key", "invoice_key"} <= cols
