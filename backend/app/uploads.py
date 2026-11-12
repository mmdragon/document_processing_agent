"""Safe handling of uploaded files.

Rules:
- Only PDF, PNG and JPEG are accepted, checked by extension AND file signature.
- The client's file name is kept only as display metadata; the stored name is a
  server-generated UUID, so client paths are never used.
- Files are streamed to a temporary ``.part`` file with a hard size limit and only
  renamed into place after every check passes. Any failure deletes the partial file.
- PDFs and images are opened (never executed) to confirm they are structurally valid,
  not password-protected, and within the page limit.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePath

import pymupdf
from fastapi import UploadFile

from app.config import Settings

pymupdf.TOOLS.mupdf_display_errors(False)  # keep MuPDF noise out of logs

_CHUNK = 64 * 1024

# extension -> (allowed signatures, canonical content type)
FILE_TYPES: dict[str, tuple[tuple[bytes, ...], str]] = {
    ".pdf": ((b"%PDF-",), "application/pdf"),
    ".png": ((b"\x89PNG\r\n\x1a\n",), "image/png"),
    ".jpg": ((b"\xff\xd8\xff",), "image/jpeg"),
    ".jpeg": ((b"\xff\xd8\xff",), "image/jpeg"),
}


class UploadRejected(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class StoredFile:
    document_id: str
    stored_path: Path
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    page_count: int


def safe_display_name(filename: str | None) -> str:
    """Strip any directory parts and control characters from a client file name."""
    name = PurePath((filename or "").replace("\\", "/")).name
    name = "".join(ch for ch in name if ch.isprintable())
    if len(name) > 255:
        suffix = PurePath(name).suffix[:16]
        name = name[: 255 - len(suffix)] + suffix
    return name or "unnamed"


def inspect_document(path: Path, ext: str, max_pages: int) -> int:
    """Open the file read-only and return its page count, or raise UploadRejected."""
    try:
        doc = pymupdf.open(path, filetype=ext.lstrip("."))
    except Exception as exc:
        raise UploadRejected(422, "malformed_file", "The file could not be read.") from exc
    with doc:
        if doc.needs_pass:
            raise UploadRejected(422, "encrypted_pdf", "Password-protected PDFs are not supported.")
        page_count = doc.page_count
    if page_count == 0:
        raise UploadRejected(422, "no_pages", "The document has no pages.")
    if page_count > max_pages:
        raise UploadRejected(422, "too_many_pages", f"Documents are limited to {max_pages} pages.")
    return page_count


async def save_upload(file: UploadFile, settings: Settings) -> StoredFile:
    original_name = safe_display_name(file.filename)
    ext = PurePath(original_name).suffix.lower()
    if ext not in FILE_TYPES:
        raise UploadRejected(415, "unsupported_type", "Only PDF, PNG, or JPEG files are accepted.")
    signatures, content_type = FILE_TYPES[ext]

    document_id = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    part = settings.upload_dir / f"{document_id}.part"
    final = settings.upload_dir / f"{document_id}{ext}"

    size = 0
    header = b""
    digest = hashlib.sha256()
    try:
        with part.open("xb") as out:
            while chunk := await file.read(_CHUNK):
                if len(header) < 16:
                    header += chunk[: 16 - len(header)]
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise UploadRejected(
                        413,
                        "file_too_large",
                        f"File exceeds the {settings.max_upload_bytes}-byte limit.",
                    )
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise UploadRejected(400, "empty_file", "File is empty.")
        if not header.startswith(signatures):
            raise UploadRejected(
                415, "signature_mismatch", "File contents do not match its extension."
            )
        page_count = inspect_document(part, ext, settings.max_pages)
        part.rename(final)
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    return StoredFile(
        document_id=document_id,
        stored_path=final,
        original_filename=original_name,
        content_type=content_type,
        size_bytes=size,
        sha256=digest.hexdigest(),
        page_count=page_count,
    )
