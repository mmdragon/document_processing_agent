"""SQLite persistence for document records (stdlib sqlite3, one connection per call)."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.extraction.models import ExtractionResult
from app.schemas.documents import DocumentDetail, DocumentSummary, ProcessingStatus

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
    extraction_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents (uploaded_at);
"""

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
                f"SELECT {_SUMMARY_COLS}, extraction_json FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        d = self._summary_dict(row)
        raw = d.pop("extraction_json")
        d["extraction"] = ExtractionResult.model_validate_json(raw) if raw else None
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

    def save_extraction(
        self,
        document_id: str,
        *,
        status: ProcessingStatus,
        extraction: ExtractionResult | None,
        error: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET status = ?, extraction_method = ?, error = ?, "
                "extraction_json = ?, updated_at = ? WHERE id = ?",
                (
                    status,
                    extraction.method if extraction else None,
                    error,
                    extraction.model_dump_json() if extraction else None,
                    _now(),
                    document_id,
                ),
            )
