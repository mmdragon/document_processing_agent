"""SQLite persistence for document records (stdlib sqlite3, one connection per call)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.extraction.models import ExtractionResult
from app.schemas.documents import DocumentDetail, DocumentSummary, ProcessingStatus
from app.schemas.invoice import DuplicateCandidate, InvoiceFields, ValidationResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id                TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_filename   TEXT NOT NULL,
    content_type      TEXT NOT NULL,
    size_bytes        INTEGER NOT NULL,
    sha256            TEXT NOT NULL,
    page_count        INTEGER NOT NULL,
    uploaded_at       TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    status            TEXT NOT NULL,
    extraction_method TEXT,
    error             TEXT,
    extraction_json   TEXT,
    fields_json       TEXT,
    validation_json   TEXT,
    vendor_key        TEXT,
    invoice_key       TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents (uploaded_at);
"""

# Columns added after Phase 3; older local databases get them via ALTER TABLE.
_ADDED_COLUMNS = ("fields_json", "validation_json", "vendor_key", "invoice_key")

_SUMMARY_COLS = (
    "id, original_filename, content_type, size_bytes, sha256, page_count, "
    "uploaded_at, updated_at, status, extraction_method, error"
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DocumentRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            existing = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
            for col in _ADDED_COLUMNS:
                if col not in existing:
                    conn.execute(f"ALTER TABLE documents ADD COLUMN {col} TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_dupkey "
                "ON documents (vendor_key, invoice_key)"
            )

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:  # commits or rolls back
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _summary_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["document_id"] = d.pop("id")
        return d

    def create(
        self,
        *,
        document_id: str,
        original_filename: str,
        stored_filename: str,
        content_type: str,
        size_bytes: int,
        sha256: str,
        page_count: int,
    ) -> DocumentSummary:
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO documents (id, original_filename, stored_filename, content_type, "
                "size_bytes, sha256, page_count, uploaded_at, updated_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded')",
                (
                    document_id,
                    original_filename,
                    stored_filename,
                    content_type,
                    size_bytes,
                    sha256,
                    page_count,
                    now,
                    now,
                ),
            )
        summary = self.get_summary(document_id)
        assert summary is not None
        return summary

    def list(self) -> list[DocumentSummary]:
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_SUMMARY_COLS} FROM documents ORDER BY uploaded_at DESC"
            ).fetchall()
        return [DocumentSummary.model_validate(self._summary_dict(r)) for r in rows]

    def get_summary(self, document_id: str) -> DocumentSummary | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_SUMMARY_COLS} FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return DocumentSummary.model_validate(self._summary_dict(row)) if row else None

    def get_detail(self, document_id: str) -> DocumentDetail | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {_SUMMARY_COLS}, extraction_json, fields_json, validation_json "
                "FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        d = self._summary_dict(row)
        raw = d.pop("extraction_json")
        d["extraction"] = ExtractionResult.model_validate_json(raw) if raw else None
        raw = d.pop("fields_json")
        d["fields"] = InvoiceFields.model_validate_json(raw) if raw else None
        raw = d.pop("validation_json")
        d["validation"] = ValidationResult.model_validate_json(raw) if raw else None
        return DocumentDetail.model_validate(d)

    def get_stored_filename(self, document_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT stored_filename FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return row["stored_filename"] if row else None

    def set_status(self, document_id: str, status: ProcessingStatus) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), document_id),
            )

    def get_sha256(self, document_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sha256 FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return row["sha256"] if row else None

    def find_duplicates(
        self,
        document_id: str,
        *,
        vendor_key: str | None,
        invoice_key: str | None,
        sha256: str,
    ) -> list[DuplicateCandidate]:
        """Other documents with the same vendor + invoice number, or the identical file."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, original_filename, uploaded_at, sha256, fields_json, "
                "(vendor_key = ? AND invoice_key = ?) AS same_key "
                "FROM documents WHERE id != ? AND status != 'failed' AND ("
                "  (vendor_key IS NOT NULL AND invoice_key IS NOT NULL "
                "   AND vendor_key = ? AND invoice_key = ?) OR sha256 = ?"
                ") ORDER BY uploaded_at",
                (vendor_key, invoice_key, document_id, vendor_key, invoice_key, sha256),
            ).fetchall()
        result = []
        for r in rows:
            fields = (
                InvoiceFields.model_validate_json(r["fields_json"]) if r["fields_json"] else None
            )
            result.append(
                DuplicateCandidate(
                    reason="same_vendor_and_number" if r["same_key"] else "identical_file",
                    document_id=r["id"],
                    original_filename=r["original_filename"],
                    uploaded_at=r["uploaded_at"],
                    vendor_name=fields.vendor_name.value if fields else None,
                    invoice_number=fields.invoice_number.value if fields else None,
                    sha256=r["sha256"],
                )
            )
        return result

    def save_results(
        self,
        document_id: str,
        *,
        status: ProcessingStatus,
        extraction: ExtractionResult | None,
        fields: InvoiceFields | None,
        validation: ValidationResult | None,
        vendor_key: str | None,
        invoice_key: str | None,
        error: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, extraction_method = ?, error = ?, "
                "extraction_json = ?, fields_json = ?, validation_json = ?, vendor_key = ?, "
                "invoice_key = ?, updated_at = ? WHERE id = ?",
                (
                    status,
                    extraction.method if extraction else None,
                    error,
                    extraction.model_dump_json() if extraction else None,
                    fields.model_dump_json() if fields else None,
                    validation.model_dump_json() if validation else None,
                    vendor_key,
                    invoice_key,
                    _now(),
                    document_id,
                ),
            )
