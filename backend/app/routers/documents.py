"""Document upload and management endpoints."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.metrics import metrics
from app.models.db_models import Document
from app.models.schemas import DocumentResponse
from app.utils.file_handler import FileValidationError, save_upload
from app.utils.mime import mime_matches_extension, sniff_mime

router = APIRouter(prefix="/api/documents", tags=["Documents"])


# Per-route rate limits are enforced by the global SlowAPIMiddleware using
# the default limit (60/minute/IP) set in app/main.py. Endpoints that need
# a tighter override can use the @limiter.limit("N/minute") decorator from
# a module-level Limiter instance; we keep the default here to avoid the
# slowapi callable-vs-string friction across versions.


@router.post(
    "/",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Upload a document (PDF or image) for extraction.

    The upload is validated twice: once on the declared extension and
    content type (cheap, runs first), then again on the actual magic
    bytes after the file is on disk. Uploads whose magic bytes do not
    match the declared extension are rejected.
    """
    try:
        saved_name, file_path, file_size = await save_upload(file)
    except FileValidationError as exc:
        metrics.uploads_total.labels(file_type="unknown", outcome="rejected").inc()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Magic-byte verification. Always re-validates regardless of the
    # declared content type or extension. The extension and verified
    # type must agree.
    try:
        verified_type = sniff_mime(Path(file_path))
    except FileValidationError as exc:
        metrics.uploads_total.labels(file_type="unknown", outcome="magic_mismatch").inc()
        Path(file_path).unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    declared_ext = Path(file.filename or "").suffix.lstrip(".")
    if not mime_matches_extension(verified_type, declared_ext):
        metrics.uploads_total.labels(file_type=verified_type, outcome="magic_mismatch").inc()
        Path(file_path).unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Declared extension '{declared_ext}' does not match the verified file "
                f"type '{verified_type}'."
            ),
        )

    metrics.uploads_total.labels(file_type=verified_type, outcome="accepted").inc()
    doc = Document(
        filename=saved_name,
        original_filename=file.filename or "unknown",
        file_path=file_path,
        file_type=verified_type,
        file_size=file_size,
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return doc


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(
    db: AsyncSession = Depends(get_db),
) -> list[Document]:
    """List all uploaded documents."""
    result = await db.execute(select(Document).order_by(Document.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> Document:
    """Get a single document by ID."""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a document and its file."""
    from pathlib import Path

    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    path = Path(doc.file_path)
    if path.exists():
        path.unlink()

    await db.delete(doc)
