"""Document endpoints: upload, list, detail, process, corrections, review, file."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi import Path as PathParam
from fastapi.responses import FileResponse

from app.dependencies import ExtractorDep, RepositoryDep, SettingsDep
from app.processing import process_document
from app.review import CorrectionError, build_corrections, validate_and_store
from app.schemas.documents import (
    CorrectionsRequest,
    DocumentDetail,
    DocumentSummary,
    ReviewRequest,
)
from app.schemas.invoice import InvoiceFields
from app.uploads import UploadRejected, save_upload

router = APIRouter(tags=["documents"])

DocumentId = Annotated[str, PathParam(pattern=r"^[0-9a-f]{32}$")]


@router.post(
    "/documents",
    response_model=DocumentSummary,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile, settings: SettingsDep, repo: RepositoryDep
) -> DocumentSummary:
    try:
        stored = await save_upload(file, settings)
    except UploadRejected as exc:
        raise HTTPException(exc.status_code, {"code": exc.code, "message": exc.message}) from exc
    try:
        return repo.create(
            document_id=stored.document_id,
            original_filename=stored.original_filename,
            stored_filename=stored.stored_path.name,
            content_type=stored.content_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            page_count=stored.page_count,
        )
    except BaseException:
        stored.stored_path.unlink(missing_ok=True)
        raise


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(repo: RepositoryDep) -> list[DocumentSummary]:
    return repo.list()


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(document_id: DocumentId, repo: RepositoryDep) -> DocumentDetail:
    detail = repo.get_detail(document_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return detail


@router.post("/documents/{document_id}/process", response_model=DocumentDetail)
def process(
    document_id: DocumentId,
    settings: SettingsDep,
    repo: RepositoryDep,
    extractor: ExtractorDep,
) -> DocumentDetail:
    summary = repo.get_summary(document_id)
    if summary is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    if summary.status in ("processing", "reviewed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Document is {summary.status}; it cannot be reprocessed."
        )
    stored_filename = repo.get_stored_filename(document_id)
    assert stored_filename is not None
    return process_document(document_id, settings.upload_dir / stored_filename, repo, extractor)


@router.post("/documents/{document_id}/corrections", response_model=DocumentDetail)
def add_corrections(
    document_id: DocumentId, body: CorrectionsRequest, repo: RepositoryDep
) -> DocumentDetail:
    """Record reviewer corrections and re-run validation. Extracted values are kept."""
    detail = _require(repo, document_id)
    if detail.status in ("reviewed", "processing"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Document is {detail.status}; reopen it to edit."
        )
    if detail.fields is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Process the document before correcting it.")
    try:
        new = build_corrections(detail.fields, body.corrections)
    except CorrectionError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"code": "invalid_correction", "field": exc.field, "message": exc.message},
        ) from exc
    repo.append_corrections(document_id, new)
    new_status, validation, v_key, i_key = validate_and_store(
        document_id,
        repo,
        fields=detail.fields,
        corrections=detail.corrections + new,
        extraction_method=detail.extraction_method or "none",
    )
    repo.save_validation(
        document_id, status=new_status, validation=validation, vendor_key=v_key, invoice_key=i_key
    )
    return _require(repo, document_id)


@router.post("/documents/{document_id}/review", response_model=DocumentDetail)
def review(document_id: DocumentId, body: ReviewRequest, repo: RepositoryDep) -> DocumentDetail:
    """Mark a document reviewed (a person checked the data) or reopen it.

    Reviewing records a human check of the extracted data. It does not approve payment.
    """
    detail = _require(repo, document_id)
    if detail.status in ("uploaded", "processing", "failed"):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"A document that is {detail.status} cannot be reviewed."
        )
    if body.reviewed:
        repo.set_review(
            document_id,
            status="reviewed",
            reviewed_at=datetime.now(UTC).isoformat(),
            note=body.note,
        )
    else:
        if detail.status != "reviewed":
            raise HTTPException(status.HTTP_409_CONFLICT, "Document is not reviewed.")
        reopened, *_ = validate_and_store(
            document_id,
            repo,
            fields=detail.fields or InvoiceFields(),
            corrections=detail.corrections,
            extraction_method=detail.extraction_method or "none",
        )
        repo.set_review(document_id, status=reopened, reviewed_at=None, note=body.note)
    return _require(repo, document_id)


@router.get("/documents/{document_id}/file")
def get_file(document_id: DocumentId, settings: SettingsDep, repo: RepositoryDep) -> FileResponse:
    """Serve the original upload read-only, for side-by-side review."""
    summary = repo.get_summary(document_id)
    stored = repo.get_stored_filename(document_id)
    if summary is None or stored is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    path = settings.upload_dir / stored
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Stored file is missing.")
    return FileResponse(
        path,
        media_type=summary.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{stored}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


def _require(repo, document_id: str) -> DocumentDetail:
    detail = repo.get_detail(document_id)
    if detail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return detail
