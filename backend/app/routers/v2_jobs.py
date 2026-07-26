"""Clean V2 API for the OpenAI-only grounded document pipeline."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Annotated, Any, Protocol

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.config import settings as app_settings
from app.database import get_db
from app.models.db_models import Artifact, ExtractionSchema, PageCheckpoint, ParseJob
from app.models.enums import JobStatus, PageStatus
from app.services.parsing.ingest import DocumentInputError, inspect_document
from app.services.parsing.storage import FileStore, ObjectStore
from app.services.parsing.v2_contracts import DocumentResult, ProcessingMode
from app.services.parsing.v2_evaluation import GroundedEvaluationReport, evaluate_grounded_document

router = APIRouter(prefix="/api/v2/jobs", tags=["v2-jobs"], dependencies=[Depends(require_api_key)])


class V2Queue(Protocol):
    async def submit(self, job_id: str) -> None: ...


class V2Settings(BaseModel):
    mode: ProcessingMode = ProcessingMode.BALANCED
    segment_documents: bool = True
    extraction_schema_id: str | None = None


class V2JobResponse(BaseModel):
    id: str
    original_filename: str
    source_mime: str
    source_size: int
    source_sha256: str
    page_count: int
    status: str
    settings: V2Settings
    models: dict[str, str]
    completed_pages: int
    failed_pages: int
    error_code: str | None = None
    error_message: str | None = None
    usage: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = []


class V2JobListResponse(BaseModel):
    items: list[V2JobResponse]


def get_v2_store() -> ObjectStore:
    return FileStore(app_settings.artifacts_path)


def get_v2_queue() -> V2Queue:
    from app.services.v2_jobs import get_v2_job_queue

    return get_v2_job_queue()


def _error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _serialize(job: ParseJob) -> V2JobResponse:
    artifact_items = [
        {
            "id": item.id,
            "type": item.type,
            "mime_type": item.mime_type,
            "size": item.size,
            "sha256": item.sha256,
            "download_url": f"/api/v2/jobs/{job.id}/artifacts/{item.id}",
        }
        for item in job.artifacts
    ]
    usage = (job.quality_policy_snapshot or {}).get("usage")
    return V2JobResponse(
        id=job.id,
        original_filename=job.original_filename,
        source_mime=job.source_mime,
        source_size=job.source_size,
        source_sha256=job.source_sha256,
        page_count=job.page_count,
        status=str(job.status),
        settings=V2Settings.model_validate(job.settings),
        models={"draft": "gpt-5.6-luna", "verification": "gpt-5.6-terra"},
        completed_pages=job.completed_pages,
        failed_pages=job.failed_pages,
        error_code=job.error_code,
        error_message=job.error_message,
        usage=usage,
        artifacts=artifact_items,
    )


async def _job(db: AsyncSession, job_id: str) -> ParseJob:
    item = await db.scalar(
        select(ParseJob)
        .where(ParseJob.id == job_id)
        .options(selectinload(ParseJob.pages), selectinload(ParseJob.artifacts))
    )
    if item is None:
        raise _error("job_not_found", "Job was not found", 404)
    return item


@router.post("", response_model=V2JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_v2_job(
    file: Annotated[UploadFile, File()],
    settings_json: Annotated[str, Form(alias="settings")] = "{}",
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_v2_store),
    queue: V2Queue = Depends(get_v2_queue),
) -> V2JobResponse:
    if not app_settings.openai_api_key:
        raise _error("openai_not_configured", "OPENAI_API_KEY is required for V2 parsing", 503)
    try:
        parse_settings = V2Settings.model_validate_json(settings_json or "{}")
    except ValueError as exc:
        raise _error("invalid_settings", str(exc)) from exc
    extraction_schema = None
    extraction_snapshot = None
    if parse_settings.extraction_schema_id:
        extraction_schema = await db.get(ExtractionSchema, parse_settings.extraction_schema_id)
        if extraction_schema is None:
            raise _error("extraction_schema_not_found", "Extraction schema was not found")
        extraction_snapshot = {
            "id": extraction_schema.id,
            "name": extraction_schema.name,
            "version": extraction_schema.version,
            "schema_sha256": extraction_schema.schema_sha256,
            "json_schema": extraction_schema.schema_json,
        }
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > app_settings.max_upload_bytes:
            raise _error("too_large", "Document exceeds the upload limit", 413)
        chunks.append(chunk)
    data = b"".join(chunks)
    filename = Path(file.filename or "document").name
    try:
        inspected = inspect_document(
            data, filename, app_settings.max_upload_bytes, app_settings.max_document_pages
        )
    except DocumentInputError as exc:
        raise _error(exc.code, str(exc)) from exc
    job_id = uuid.uuid4().hex
    suffix = Path(filename).suffix.lower()
    source_path = f"jobs-v2/{job_id}/source{suffix}"
    store.write(source_path, data)
    job = ParseJob(
        id=job_id,
        original_filename=filename,
        source_path=source_path,
        source_mime=inspected.mime_type,
        source_size=len(data),
        source_sha256=hashlib.sha256(data).hexdigest(),
        page_count=inspected.page_count,
        status=JobStatus.QUEUED,
        settings=parse_settings.model_dump(mode="json"),
        model_name="gpt-5.6-luna",
        review_model_name="gpt-5.6-terra",
        extraction_schema_id=extraction_schema.id if extraction_schema else None,
        extraction_schema_snapshot=extraction_snapshot,
        extraction_model_name="gpt-5.6-terra" if extraction_schema else None,
        pages=[
            PageCheckpoint(page_number=page, status=PageStatus.PENDING)
            for page in range(1, inspected.page_count + 1)
        ],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await queue.submit(job_id)
    return _serialize(job)


@router.get("", response_model=V2JobListResponse)
async def list_v2_jobs(db: AsyncSession = Depends(get_db)) -> V2JobListResponse:
    jobs = list(
        (
            await db.execute(
                select(ParseJob)
                .options(selectinload(ParseJob.pages), selectinload(ParseJob.artifacts))
                .order_by(ParseJob.created_at.desc())
            )
        )
        .scalars()
        .unique()
    )
    return V2JobListResponse(items=[_serialize(job) for job in jobs])


@router.get("/{job_id}", response_model=V2JobResponse)
async def get_v2_job(job_id: str, db: AsyncSession = Depends(get_db)) -> V2JobResponse:
    return _serialize(await _job(db, job_id))


@router.post("/{job_id}/cancel", response_model=V2JobResponse)
async def cancel_v2_job(job_id: str, db: AsyncSession = Depends(get_db)) -> V2JobResponse:
    job = await _job(db, job_id)
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
    elif job.status in {JobStatus.INSPECTING, JobStatus.PROCESSING, JobStatus.ASSEMBLING}:
        job.cancel_requested = True
        job.status = JobStatus.CANCELLING
    else:
        raise _error("invalid_state", f"Cannot cancel a job in {job.status} state", 409)
    await db.commit()
    return _serialize(job)


@router.get("/{job_id}/artifacts/{artifact_id}")
async def download_v2_artifact(
    job_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_v2_store),
) -> Response:
    artifact = await db.scalar(
        select(Artifact).where(Artifact.id == artifact_id, Artifact.job_id == job_id)
    )
    if artifact is None:
        raise _error("artifact_not_found", "Artifact was not found", 404)
    filename = Path(artifact.relative_path).name
    return Response(
        content=store.read(artifact.relative_path),
        media_type=artifact.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{job_id}/evaluate", response_model=GroundedEvaluationReport)
async def evaluate_v2_job(
    job_id: str,
    labels: Annotated[UploadFile, File()],
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_v2_store),
) -> GroundedEvaluationReport:
    job = await _job(db, job_id)
    document_artifact = next(
        (artifact for artifact in job.artifacts if artifact.type == "document_json"), None
    )
    if document_artifact is None:
        raise _error("document_not_ready", "Grounded document artifact is not ready", 409)
    try:
        predicted = DocumentResult.model_validate_json(store.read(document_artifact.relative_path))
        expected = DocumentResult.model_validate_json(await labels.read())
    except ValueError as exc:
        raise _error("invalid_evaluation_labels", str(exc)) from exc
    return evaluate_grounded_document(predicted, expected)
