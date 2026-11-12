"""Document endpoints: upload, list, detail, process."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi import Path as PathParam

from app.dependencies import ExtractorDep, RepositoryDep, SettingsDep
from app.processing import process_document
from app.schemas.documents import DocumentDetail, DocumentSummary
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
