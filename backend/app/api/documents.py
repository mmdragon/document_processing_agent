"""Document endpoints.

Phase 1 skeleton: accepts an upload, checks type/size, and stores it under a
server-generated name. Persistence, listing, and processing arrive in later phases.
"""

import uuid
from datetime import UTC, datetime
from pathlib import PurePath
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from app.config import Settings, get_settings
from app.schemas.documents import DocumentUploadResponse

router = APIRouter(tags=["documents"])

# File signatures ("magic bytes") for the types we accept.
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
}
_CHUNK = 64 * 1024


@router.post(
    "/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile, settings: Annotated[Settings, Depends(get_settings)]
) -> DocumentUploadResponse:
    # Only the extension of the client-supplied name is used; the path is never trusted.
    original_name = PurePath(file.filename or "").name
    ext = PurePath(original_name).suffix.lower()
    if ext not in _SIGNATURES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only PDF, PNG, or JPEG files are accepted."
        )

    document_id = uuid.uuid4().hex
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.upload_dir / f"{document_id}{ext}"

    size = 0
    header = b""
    try:
        with dest.open("xb") as out:
            while chunk := await file.read(_CHUNK):
                if not header:
                    header = chunk[:16]
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(
                        status.HTTP_413_CONTENT_TOO_LARGE,
                        f"File exceeds {settings.max_upload_bytes} bytes.",
                    )
                out.write(chunk)
        if size == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "File is empty.")
        if not header.startswith(_SIGNATURES[ext]):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "File contents do not match its extension.",
            )
    except BaseException:
        dest.unlink(missing_ok=True)
        raise

    return DocumentUploadResponse(
        document_id=document_id,
        original_filename=original_name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=size,
        uploaded_at=datetime.now(UTC),
    )
