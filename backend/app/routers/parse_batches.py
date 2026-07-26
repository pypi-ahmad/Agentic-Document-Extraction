"""Durable multi-document submission and combined bundle export."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.config import settings as app_settings
from app.database import get_db
from app.models.db_models import (
    ExtractionSchema,
    PageCheckpoint,
    ParseBatch,
    ParseJob,
    SubDocument,
)
from app.models.enums import ArtifactType, JobStatus, PageStatus
from app.models.schemas import ParseJobResponse, ParseSettings
from app.routers.parse_jobs import _error, _serialize, get_job_queue, get_object_store
from app.services.jobs import ParseJobQueue
from app.services.parsing.ingest import DocumentInputError, inspect_document
from app.services.parsing.quality_policy import resolve_quality_policy
from app.services.parsing.storage import ObjectStore

router = APIRouter(
    prefix="/api/parse-batches",
    tags=["parse-batches"],
    dependencies=[Depends(require_api_key)],
)

TERMINAL = {
    JobStatus.CANCELLED,
    JobStatus.COMPLETED,
    JobStatus.COMPLETED_WITH_WARNINGS,
    JobStatus.FAILED,
    JobStatus.PAUSED,
}
SUCCESSFUL = {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}


class ParseBatchResponse(BaseModel):
    id: str
    status: str
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    cancelled_jobs: int
    bundle_ready: bool
    bundle_url: str | None = None
    created_at: str | None = None
    completed_at: str | None = None
    jobs: list[ParseJobResponse] = Field(default_factory=list)


class ParseBatchListResponse(BaseModel):
    items: list[ParseBatchResponse]


def _batch_statement(batch_id: str | None = None):
    statement = select(ParseBatch).options(
        selectinload(ParseBatch.jobs).selectinload(ParseJob.pages),
        selectinload(ParseBatch.jobs).selectinload(ParseJob.artifacts),
        selectinload(ParseBatch.jobs)
        .selectinload(ParseJob.subdocuments)
        .selectinload(SubDocument.artifacts),
        selectinload(ParseBatch.jobs).selectinload(ParseJob.review_cases),
    )
    return statement.where(ParseBatch.id == batch_id) if batch_id else statement


async def _batch_or_404(db: AsyncSession, batch_id: str) -> ParseBatch:
    batch = (await db.execute(_batch_statement(batch_id))).scalar_one_or_none()
    if batch is None:
        raise _error("batch_not_found", "Parse batch was not found", 404)
    return batch


def _status(batch: ParseBatch) -> tuple[str, bool]:
    statuses = [job.status for job in batch.jobs]
    all_terminal = bool(statuses) and all(value in TERMINAL for value in statuses)
    if not all_terminal:
        return ("processing" if any(value != JobStatus.QUEUED for value in statuses) else "queued", False)
    if any(value in {JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.PAUSED} for value in statuses):
        return "completed_with_warnings", True
    return "completed", True


def _serialize_batch(batch: ParseBatch) -> ParseBatchResponse:
    batch_status, terminal = _status(batch)
    return ParseBatchResponse(
        id=batch.id,
        status=batch_status,
        total_jobs=len(batch.jobs),
        completed_jobs=sum(job.status in SUCCESSFUL for job in batch.jobs),
        failed_jobs=sum(job.status in {JobStatus.FAILED, JobStatus.PAUSED} for job in batch.jobs),
        cancelled_jobs=sum(job.status == JobStatus.CANCELLED for job in batch.jobs),
        bundle_ready=terminal and any(job.status in SUCCESSFUL for job in batch.jobs),
        bundle_url=(
            f"/api/parse-batches/{batch.id}/bundle"
            if terminal and any(job.status in SUCCESSFUL for job in batch.jobs)
            else None
        ),
        created_at=batch.created_at.isoformat() if batch.created_at else None,
        completed_at=batch.completed_at.isoformat() if batch.completed_at else None,
        jobs=[_serialize(job) for job in batch.jobs],
    )


async def _read_files(files: list[UploadFile]) -> list[dict[str, Any]]:
    if not files or len(files) > app_settings.max_batch_files:
        raise _error(
            "invalid_batch_size",
            f"Choose between 1 and {app_settings.max_batch_files} documents",
        )
    prepared: list[dict[str, Any]] = []
    total_bytes = 0
    max_total = app_settings.max_batch_size_mb * 1024 * 1024
    for upload in files:
        name = Path(upload.filename or "document").name
        chunks: list[bytes] = []
        size = 0
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            total_bytes += len(chunk)
            if size > app_settings.max_upload_bytes:
                raise _error("too_large", f"{name} exceeds {app_settings.max_upload_size_mb} MB", 413)
            if total_bytes > max_total:
                raise _error(
                    "batch_too_large",
                    f"Batch exceeds {app_settings.max_batch_size_mb} MB",
                    413,
                )
            chunks.append(chunk)
        data = b"".join(chunks)
        try:
            inspected = inspect_document(
                data,
                name,
                app_settings.max_upload_bytes,
                app_settings.max_document_pages,
            )
        except DocumentInputError as exc:
            raise _error(exc.code, f"{name}: {exc}") from exc
        prepared.append({"name": name, "data": data, "inspected": inspected})
    return prepared


@router.post("", response_model=ParseBatchResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_parse_batch(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    settings_json: Annotated[str, Form(alias="settings")] = "{}",
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    queue: ParseJobQueue = Depends(get_job_queue),
) -> ParseBatchResponse:
    try:
        parse_settings = ParseSettings.model_validate_json(settings_json or "{}")
    except ValueError as exc:
        raise _error("invalid_settings", str(exc)) from exc
    prepared = await _read_files(files)
    if queue.in_flight + len(prepared) > app_settings.job_queue_max_depth:
        raise _error("queue_full", "Batch exceeds available queue capacity", 503)
    runtime = getattr(request.app.state, "parser_runtime", None)
    if runtime is not None and not (paddle_status := await runtime.paddleocr_vl.status()).available:
        raise _error(
            "paddleocr_vl_unavailable",
            paddle_status.error or "PaddleOCR-VL Docker runtime is unavailable.",
            503,
        )
    schema = None
    schema_snapshot = None
    if parse_settings.extraction_schema_id:
        schema = await db.get(ExtractionSchema, parse_settings.extraction_schema_id)
        if schema is None:
            raise _error("extraction_schema_not_found", "Selected extraction schema was not found")
        schema_snapshot = {
            "id": schema.id,
            "name": schema.name,
            "description": schema.description,
            "version": schema.version,
            "json_schema": schema.schema_json,
            "schema_sha256": schema.schema_sha256,
        }
    for item in prepared:
        if parse_settings.end_page and parse_settings.end_page > item["inspected"].page_count:
            raise _error("invalid_page_range", f"{item['name']}: end_page exceeds page count")

    batch = ParseBatch(
        id=uuid.uuid4().hex,
        settings=parse_settings.model_dump(mode="json"),
        status="queued",
    )
    policy = resolve_quality_policy(
        parse_settings.processing_mode,
        parse_settings.document_profile,
        parse_settings.quality_overrides,
    )
    written_job_ids: list[str] = []
    try:
        for ordinal, item in enumerate(prepared, start=1):
            job_id = uuid.uuid4().hex
            written_job_ids.append(job_id)
            suffix = Path(item["name"]).suffix.lower()
            source_path = f"jobs/{job_id}/source{suffix}"
            store.write(source_path, item["data"])
            end_page = parse_settings.end_page or item["inspected"].page_count
            batch.jobs.append(
                ParseJob(
                    id=job_id,
                    batch_ordinal=ordinal,
                    original_filename=item["name"],
                    source_path=source_path,
                    source_mime=item["inspected"].mime_type,
                    source_size=len(item["data"]),
                    source_sha256=hashlib.sha256(item["data"]).hexdigest(),
                    page_count=item["inspected"].page_count,
                    status=JobStatus.QUEUED,
                    settings=parse_settings.model_dump(mode="json"),
                    quality_policy_snapshot=policy.model_dump(mode="json"),
                    model_name="PaddleOCR-VL-1.6",
                    review_model_name=parse_settings.review_model,
                    extraction_schema_id=schema.id if schema else None,
                    extraction_schema_snapshot=schema_snapshot,
                    extraction_model_name=parse_settings.extraction_model,
                    pages=[
                        PageCheckpoint(page_number=page, status=PageStatus.PENDING)
                        for page in range(parse_settings.start_page, end_page + 1)
                    ],
                )
            )
        db.add(batch)
        await db.commit()
    except Exception:
        await db.rollback()
        for job_id in written_job_ids:
            store.delete_tree(f"jobs/{job_id}")
        raise
    for job in batch.jobs:
        await queue.submit(job.id)
    return _serialize_batch(await _batch_or_404(db, batch.id))


@router.get("", response_model=ParseBatchListResponse)
async def list_parse_batches(db: AsyncSession = Depends(get_db)) -> ParseBatchListResponse:
    batches = list(
        (await db.execute(_batch_statement().order_by(ParseBatch.created_at.desc()).limit(50)))
        .scalars()
        .unique()
    )
    return ParseBatchListResponse(items=[_serialize_batch(item) for item in batches])


@router.get("/{batch_id}", response_model=ParseBatchResponse)
async def get_parse_batch(
    batch_id: str, db: AsyncSession = Depends(get_db)
) -> ParseBatchResponse:
    batch = await _batch_or_404(db, batch_id)
    current_status, terminal = _status(batch)
    if batch.status != current_status:
        batch.status = current_status
        if terminal and batch.completed_at is None:
            batch.completed_at = dt.datetime.now(dt.UTC)
        await db.commit()
    return _serialize_batch(batch)


def _archive_name(job: ParseJob) -> str:
    stem = "".join(character if character.isalnum() or character in "-_" else "_" for character in Path(job.original_filename).stem)
    return f"{job.batch_ordinal or 0:03d}-{stem or 'document'}"


@router.get("/{batch_id}/bundle")
async def download_parse_batch_bundle(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> Response:
    batch = await _batch_or_404(db, batch_id)
    _, terminal = _status(batch)
    successful = [job for job in batch.jobs if job.status in SUCCESSFUL]
    if not terminal or not successful:
        raise _error("batch_not_ready", "Batch export is available after all jobs are terminal", 409)
    manifest: dict[str, Any] = {
        "schema_version": "paperplane-batch/v1",
        "batch_id": batch.id,
        "documents": [],
    }
    output = BytesIO()
    with ZipFile(output, mode="w") as archive:
        for job in batch.jobs:
            entry: dict[str, Any] = {
                "job_id": job.id,
                "ordinal": job.batch_ordinal,
                "filename": job.original_filename,
                "status": job.status,
                "error_code": job.error_code,
                "error_message": job.error_message,
            }
            bundle = next(
                (
                    artifact
                    for artifact in job.artifacts
                    if artifact.subdocument_id is None and artifact.type == ArtifactType.BUNDLE
                ),
                None,
            )
            if job.status in SUCCESSFUL and bundle:
                path = f"documents/{_archive_name(job)}/document-bundle.zip"
                info = ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                archive.writestr(info, store.read(bundle.relative_path))
                entry["bundle"] = path
                entry["verification_status"] = (
                    "verified"
                    if not any(
                        case.status == "open" and case.item_kind == "region"
                        for case in job.review_cases
                    )
                    else "draft"
                )
            manifest["documents"].append(entry)
        manifest_info = ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0))
        manifest_info.compress_type = ZIP_DEFLATED
        manifest_info.external_attr = 0o600 << 16
        archive.writestr(
            manifest_info,
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True).encode(),
        )
    data = output.getvalue()
    path = f"batches/{batch.id}/batch-bundle.zip"
    store.write(path, data)
    batch.bundle_path = path
    batch.bundle_sha256 = hashlib.sha256(data).hexdigest()
    await db.commit()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="paperplane-batch-{batch.id}.zip"'},
    )
