"""REST endpoints for local document parse jobs and artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.config import settings as app_settings
from app.constants import SSE_MAX_ITERATIONS
from app.database import get_db
from app.models.db_models import (
    Artifact,
    ExtractionSchema,
    PageCheckpoint,
    ParseJob,
    SubDocument,
)
from app.models.enums import ArtifactType, JobStatus, PageStatus
from app.models.schemas import (
    ArtifactResponse,
    ExtractionSchemaSnapshotSummary,
    PageCheckpointResponse,
    ParseJobListResponse,
    ParseJobResponse,
    ParseSettings,
    SubDocumentListResponse,
    SubDocumentSummary,
)
from app.services.jobs import ParseJobQueue
from app.services.jobs import get_job_queue as _get_job_queue
from app.services.parsing.agentic_contracts import PageDiagnostics
from app.services.parsing.ingest import DocumentInputError, inspect_document
from app.services.parsing.model_catalog import OllamaCatalogUnavailable, OllamaModelCatalog
from app.services.parsing.public_diagnostics import (
    PublicPageDiagnostics,
    to_public_diagnostics,
)
from app.services.parsing.quality_policy import resolve_quality_policy
from app.services.parsing.storage import FileStore, ObjectStore
from app.services.parsing.vision_providers import ProviderError

router = APIRouter(
    prefix="/api/parse-jobs", tags=["parse-jobs"], dependencies=[Depends(require_api_key)]
)
logger = logging.getLogger(__name__)

PREVIEWABLE_MIME_PREFIXES = ("text/", "image/")
PREVIEWABLE_MIME_TYPES = {"application/json", "application/pdf"}
ARTIFACT_ORDER: dict[str, int] = {
    ArtifactType.SOURCE_DOCUMENT: 0,
    ArtifactType.GROUNDING_PDF: 0,
    ArtifactType.CLEAN_MARKDOWN: 1,
    ArtifactType.LLM_MARKDOWN: 2,
    ArtifactType.GROUNDED_MARKDOWN: 3,
    ArtifactType.SEARCHABLE_PDF: 4,
    ArtifactType.CONTEXT_JSON: 5,
    ArtifactType.DOMAIN_EXTRACTION: 6,
    ArtifactType.SCHEMA_EXTRACTION: 6,
    ArtifactType.SCHEMA_TABLE: 7,
    ArtifactType.STRUCTURED_BLOCKS: 7,
    ArtifactType.SUBDOCUMENT_MANIFEST: 8,
    ArtifactType.DIAGNOSTICS: 7,
    ArtifactType.SETTINGS: 8,
    ArtifactType.WARNINGS: 9,
    ArtifactType.FIGURE: 10,
    ArtifactType.BUNDLE: 11,
}


def get_object_store() -> ObjectStore:
    return FileStore(app_settings.artifacts_path)


def get_job_queue() -> ParseJobQueue:
    return _get_job_queue()


def get_model_catalog(request: Request) -> OllamaModelCatalog:
    return request.app.state.parser_runtime.model_catalog


def _error(code: str, message: str, http_status: int = 422) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code, "message": message})


def _job_statement(job_id: str):
    return (
        select(ParseJob)
        .where(ParseJob.id == job_id)
        .options(
            selectinload(ParseJob.pages),
            selectinload(ParseJob.artifacts),
            selectinload(ParseJob.subdocuments).selectinload(SubDocument.artifacts),
            selectinload(ParseJob.review_cases),
            selectinload(ParseJob.reprocess_runs),
        )
    )


async def _job_or_404(db: AsyncSession, job_id: str) -> ParseJob:
    job = (await db.execute(_job_statement(job_id))).scalar_one_or_none()
    if job is None:
        raise _error("job_not_found", "Parse job was not found", 404)
    return job


def _serialize(job: ParseJob) -> ParseJobResponse:
    parsed_settings = ParseSettings.model_validate(job.settings)
    selected_last = parsed_settings.end_page or job.page_count
    selected_count = max(1, selected_last - parsed_settings.start_page + 1)
    total_batches = (selected_count + 9) // 10
    current_batch = (
        ((job.current_page - parsed_settings.start_page) // 10) + 1
        if job.current_page is not None
        else None
    )
    pages = [
        PageCheckpointResponse(
            page_number=page.page_number,
            status=page.status,
            routing=page.routing,
            warnings=page.warnings or [],
            error_code=page.error_code,
            error_message=page.error_message,
            attempts=page.attempts,
            duration_ms=page.duration_ms,
            stage=page.stage,
            quality_status=page.quality_status,
            quality_score=page.quality_score,
            repair_count=page.repair_count,
            diagnostics_url=(
                f"/api/parse-jobs/{job.id}/pages/{page.page_number}/diagnostics"
                if page.diagnostics_path
                else None
            ),
        )
        for page in job.pages
    ]
    artifacts = [
        ArtifactResponse(
            id=artifact.id,
            type=artifact.type,
            region_id=artifact.region_id,
            mime_type=artifact.mime_type,
            size=artifact.size,
            sha256=artifact.sha256,
            filename=Path(artifact.relative_path).name,
            download_url=(
                f"/api/parse-jobs/{job.id}/figures/{artifact.region_id}"
                if artifact.type == ArtifactType.FIGURE and artifact.region_id
                else (
                    f"/api/parse-jobs/{job.id}/artifact-files/{artifact.id}"
                    if artifact.type == ArtifactType.SCHEMA_TABLE
                    else f"/api/parse-jobs/{job.id}/artifacts/{artifact.type}"
                )
            ),
            preview_url=(
                (
                    f"/api/parse-jobs/{job.id}/figures/{artifact.region_id}?disposition=inline"
                    if artifact.type == ArtifactType.FIGURE and artifact.region_id
                    else f"/api/parse-jobs/{job.id}/artifacts/{artifact.type}?disposition=inline"
                )
                if artifact.mime_type.startswith(PREVIEWABLE_MIME_PREFIXES)
                or artifact.mime_type in PREVIEWABLE_MIME_TYPES
                else None
            ),
        )
        for artifact in sorted(
            (item for item in job.artifacts if item.subdocument_id is None),
            key=lambda item: (
                ARTIFACT_ORDER.get(item.type, len(ARTIFACT_ORDER)),
                item.region_id or "",
                item.relative_path,
            ),
        )
    ]
    return ParseJobResponse(
        id=job.id,
        batch_id=job.batch_id,
        batch_ordinal=job.batch_ordinal,
        original_filename=job.original_filename,
        source_mime=job.source_mime,
        source_size=job.source_size,
        source_sha256=job.source_sha256,
        page_count=job.page_count,
        status=job.status,
        settings=parsed_settings,
        quality_policy=job.quality_policy_snapshot,
        current_page=job.current_page,
        current_batch=current_batch,
        total_batches=total_batches,
        detected_profile=job.detected_profile,
        profile_confidence=job.profile_confidence,
        segmentation_status=job.segmentation_status,
        subdocument_count=len(job.subdocuments),
        is_partial=job.failed_pages > 0,
        completed_pages=job.completed_pages,
        failed_pages=job.failed_pages,
        warning_count=job.warning_count,
        review_required_count=sum(case.status == "open" for case in job.review_cases),
        source_preview_url=f"/api/parse-jobs/{job.id}/source?disposition=inline",
        output_revision=job.output_revision,
        verified_export_ready=(
            bool(job.pages)
            and all(page.status == PageStatus.COMPLETED for page in job.pages)
            and not any(
                case.status == "open" and case.item_kind == "region" for case in job.review_cases
            )
        ),
        error_code=job.error_code,
        error_message=job.error_message,
        model_name=job.model_name,
        model_digest=job.model_digest,
        review_model_name=job.review_model_name,
        review_model_digest=job.review_model_digest,
        extraction_schema=(
            ExtractionSchemaSnapshotSummary.model_validate(
                {
                    key: job.extraction_schema_snapshot[key]
                    for key in ("id", "name", "version", "schema_sha256")
                }
            )
            if job.extraction_schema_snapshot
            else None
        ),
        extraction_model_name=job.extraction_model_name,
        extraction_model_digest=job.extraction_model_digest,
        created_at=job.created_at.isoformat() if job.created_at else None,
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        pages=pages,
        artifacts=artifacts,
    )


def _serialize_subdocument(job_id: str, item: SubDocument) -> SubDocumentSummary:
    artifacts = [
        ArtifactResponse(
            id=artifact.id,
            type=artifact.type,
            region_id=artifact.region_id,
            mime_type=artifact.mime_type,
            size=artifact.size,
            sha256=artifact.sha256,
            filename=Path(artifact.relative_path).name,
            download_url=f"/api/parse-jobs/{job_id}/sub-documents/{item.id}/artifacts/{artifact.id}",
            preview_url=(
                f"/api/parse-jobs/{job_id}/sub-documents/{item.id}/artifacts/{artifact.id}?disposition=inline"
                if artifact.mime_type.startswith(PREVIEWABLE_MIME_PREFIXES)
                or artifact.mime_type in PREVIEWABLE_MIME_TYPES
                else None
            ),
        )
        for artifact in sorted(
            item.artifacts,
            key=lambda artifact: (
                ARTIFACT_ORDER.get(artifact.type, len(ARTIFACT_ORDER)),
                artifact.relative_path,
            ),
        )
    ]
    return SubDocumentSummary(
        id=item.id,
        ordinal=item.ordinal,
        start_page=item.start_page,
        end_page=item.end_page,
        profile=item.profile,
        confidence=item.confidence,
        identifiers=item.identifiers or [],
        boundary_confidence=item.boundary_confidence,
        boundary_reasons=item.boundary_reasons or [],
        complete=item.complete,
        missing_pages=item.missing_pages or [],
        warnings=item.warnings or [],
        artifacts=artifacts,
    )


@router.post("", response_model=ParseJobResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_parse_job(
    request: Request,
    file: Annotated[UploadFile, File()],
    settings_json: Annotated[str, Form(alias="settings")] = "{}",
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    queue: ParseJobQueue = Depends(get_job_queue),
    catalog: OllamaModelCatalog = Depends(get_model_catalog),
) -> ParseJobResponse:
    try:
        parse_settings = ParseSettings.model_validate_json(settings_json or "{}")
    except ValueError as exc:
        raise _error("invalid_settings", str(exc)) from exc
    extraction_schema = None
    extraction_schema_snapshot = None
    if parse_settings.extraction_schema_id:
        extraction_schema = await db.get(ExtractionSchema, parse_settings.extraction_schema_id)
        if extraction_schema is None:
            raise _error("extraction_schema_not_found", "Selected extraction schema was not found")
        extraction_schema_snapshot = {
            "id": extraction_schema.id,
            "name": extraction_schema.name,
            "description": extraction_schema.description,
            "version": extraction_schema.version,
            "json_schema": extraction_schema.schema_json,
            "schema_sha256": extraction_schema.schema_sha256,
        }
    runtime = getattr(request.app.state, "parser_runtime", None)
    review_model = None
    extraction_model = None
    try:
        if parse_settings.ocr_model and runtime is not None:
            await runtime.provider_registry.validate_selection(
                parse_settings.ocr_provider, parse_settings.ocr_model
            )
        if parse_settings.cloud_mode != "off" and parse_settings.review_model:
            if parse_settings.review_provider == "ollama":
                review_model = await catalog.require_compatible(parse_settings.review_model)
            elif runtime is not None:
                await runtime.provider_registry.validate_selection(
                    parse_settings.review_provider, parse_settings.review_model
                )
        if parse_settings.extraction_schema_id and parse_settings.extraction_model:
            if parse_settings.extraction_provider == "ollama":
                extraction_model = await catalog.require_compatible(parse_settings.extraction_model)
            elif runtime is not None:
                await runtime.provider_registry.validate_selection(
                    parse_settings.extraction_provider, parse_settings.extraction_model
                )
    except OllamaCatalogUnavailable as exc:
        raise _error("ollama_unavailable", str(exc), 503) from exc
    except ValueError as exc:
        code = str(exc)
        message = (
            "Selected model is not installed"
            if code == "model_not_available"
            else "Selected model does not support vision and completion"
        )
        raise _error(code, message) from exc
    except ProviderError as exc:
        status_code = 503 if exc.code == "provider_not_configured" else 422
        raise _error(exc.code, str(exc), status_code) from exc
    if queue.in_flight >= app_settings.job_queue_max_depth:
        raise _error("queue_full", "Too many jobs queued; try again shortly", 503)
    original_filename = Path(file.filename or "document").name
    suffix = Path(original_filename).suffix.lower()
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > app_settings.max_upload_bytes:
            raise _error("too_large", f"Document exceeds {app_settings.max_upload_size_mb} MB", 413)
        chunks.append(chunk)
    data = b"".join(chunks)
    try:
        inspected = inspect_document(
            data,
            original_filename,
            app_settings.max_upload_bytes,
            app_settings.max_document_pages,
        )
    except DocumentInputError as exc:
        raise _error(exc.code, str(exc)) from exc
    if parse_settings.end_page is not None and parse_settings.end_page > inspected.page_count:
        raise _error("invalid_page_range", "end_page exceeds the document page count")

    job_id = uuid.uuid4().hex
    source_path = f"jobs/{job_id}/source{suffix}"
    store.write(source_path, data)
    end_page = parse_settings.end_page or inspected.page_count
    policy = resolve_quality_policy(
        parse_settings.processing_mode,
        parse_settings.document_profile,
        parse_settings.quality_overrides,
    )
    job = ParseJob(
        id=job_id,
        original_filename=original_filename,
        source_path=source_path,
        source_mime=inspected.mime_type,
        source_size=len(data),
        source_sha256=hashlib.sha256(data).hexdigest(),
        page_count=inspected.page_count,
        status=JobStatus.QUEUED,
        settings=parse_settings.model_dump(),
        quality_policy_snapshot=policy.model_dump(mode="json"),
        model_name="native-text",
        model_digest=None,
        review_model_name=review_model.name if review_model else None,
        review_model_digest=review_model.digest if review_model else None,
        extraction_schema_id=extraction_schema.id if extraction_schema else None,
        extraction_schema_snapshot=extraction_schema_snapshot,
        extraction_model_name=(
            extraction_model.name if extraction_model else parse_settings.extraction_model
        ),
        extraction_model_digest=extraction_model.digest if extraction_model else None,
        pages=[
            PageCheckpoint(page_number=page_number, status=PageStatus.PENDING)
            for page_number in range(parse_settings.start_page, end_page + 1)
        ],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await queue.submit(job_id)
    return _serialize(job)


@router.get("", response_model=ParseJobListResponse)
async def list_parse_jobs(
    db: AsyncSession = Depends(get_db),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> ParseJobListResponse:
    total = int((await db.scalar(select(func.count(ParseJob.id)))) or 0)
    statement = (
        select(ParseJob)
        .options(
            selectinload(ParseJob.pages),
            selectinload(ParseJob.artifacts),
            selectinload(ParseJob.subdocuments),
        )
        .order_by(ParseJob.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    jobs = list((await db.execute(statement)).scalars().unique())
    return ParseJobListResponse(
        items=[_serialize(job) for job in jobs], total=total, offset=offset, limit=limit
    )


@router.get("/{job_id}", response_model=ParseJobResponse)
async def get_parse_job(job_id: str, db: AsyncSession = Depends(get_db)) -> ParseJobResponse:
    return _serialize(await _job_or_404(db, job_id))


@router.get("/{job_id}/sub-documents", response_model=SubDocumentListResponse)
async def list_subdocuments(
    job_id: str, db: AsyncSession = Depends(get_db)
) -> SubDocumentListResponse:
    job = await _job_or_404(db, job_id)
    return SubDocumentListResponse(
        items=[_serialize_subdocument(job.id, item) for item in job.subdocuments]
    )


@router.get("/{job_id}/sub-documents/{subdocument_id}", response_model=SubDocumentSummary)
async def get_subdocument(
    job_id: str, subdocument_id: str, db: AsyncSession = Depends(get_db)
) -> SubDocumentSummary:
    job = await _job_or_404(db, job_id)
    item = next((value for value in job.subdocuments if value.id == subdocument_id), None)
    if item is None:
        raise _error("subdocument_not_found", "Sub-document was not found", 404)
    return _serialize_subdocument(job.id, item)


@router.get("/{job_id}/sub-documents/{subdocument_id}/artifacts/{artifact_id}")
async def download_subdocument_artifact(
    job_id: str,
    subdocument_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    disposition: Literal["attachment", "inline"] = Query(default="attachment"),
) -> Response:
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.job_id == job_id,
            Artifact.subdocument_id == subdocument_id,
        )
    )
    if artifact is None:
        raise _error("artifact_not_found", "Sub-document artifact was not found", 404)
    filename = Path(artifact.relative_path).name
    return Response(
        content=store.read(artifact.relative_path),
        media_type=artifact.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get(
    "/{job_id}/pages/{page_number}/diagnostics",
    response_model=PublicPageDiagnostics,
)
async def get_page_diagnostics(
    job_id: str,
    page_number: int,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> PublicPageDiagnostics:
    job = await _job_or_404(db, job_id)
    checkpoint = next((page for page in job.pages if page.page_number == page_number), None)
    if checkpoint is None or not checkpoint.diagnostics_path:
        raise _error("diagnostics_not_found", "Page diagnostics were not found", 404)
    try:
        expected_path = f"jobs/{job.id}/checkpoints/p{page_number:04d}/diagnostics.json"
        if checkpoint.diagnostics_path != expected_path:
            raise ValueError("invalid diagnostics path")
        internal = PageDiagnostics.model_validate_json(store.read(checkpoint.diagnostics_path))
        return to_public_diagnostics(internal)
    except (KeyError, OSError, ValueError):
        raise _error("diagnostics_not_found", "Page diagnostics were not found", 404) from None


@router.post("/{job_id}/cancel", response_model=ParseJobResponse)
async def cancel_parse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> ParseJobResponse:
    job = await _job_or_404(db, job_id)
    if job.status == JobStatus.QUEUED:
        job.status = JobStatus.CANCELLED
    elif job.status in {JobStatus.INSPECTING, JobStatus.PROCESSING, JobStatus.ASSEMBLING}:
        job.cancel_requested = True
        job.status = JobStatus.CANCELLING
    else:
        raise _error("invalid_state", f"Cannot cancel a job in {job.status} state", 409)
    await db.commit()
    return _serialize(job)


@router.post("/{job_id}/resume", response_model=ParseJobResponse)
async def resume_parse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    queue: ParseJobQueue = Depends(get_job_queue),
) -> ParseJobResponse:
    job = await _job_or_404(db, job_id)
    if job.status not in {JobStatus.PAUSED, JobStatus.CANCELLED, JobStatus.FAILED}:
        raise _error("invalid_state", f"Cannot resume a job in {job.status} state", 409)
    ParseSettings.model_validate(job.settings)
    job.status = JobStatus.QUEUED
    job.cancel_requested = False
    job.error_code = None
    job.error_message = None
    await db.commit()
    await queue.submit(job_id)
    return _serialize(job)


@router.post("/{job_id}/retry-failed", response_model=ParseJobResponse)
async def retry_failed_pages(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    queue: ParseJobQueue = Depends(get_job_queue),
) -> ParseJobResponse:
    job = await _job_or_404(db, job_id)
    failed = [page for page in job.pages if page.status == PageStatus.FAILED]
    if not failed or job.status not in {JobStatus.FAILED, JobStatus.COMPLETED_WITH_WARNINGS}:
        raise _error("invalid_state", "Job has no retryable failed pages", 409)
    ParseSettings.model_validate(job.settings)
    for page in failed:
        page.status = PageStatus.PENDING
        page.error_code = None
        page.error_message = None
    job.status = JobStatus.QUEUED
    job.failed_pages = 0
    job.error_code = None
    job.error_message = None
    await db.commit()
    await queue.submit(job_id)
    return _serialize(job)


async def _artifact_or_404(db: AsyncSession, job_id: str, artifact_type: str) -> Artifact:
    artifact = await db.scalar(
        select(Artifact).where(Artifact.job_id == job_id, Artifact.type == artifact_type)
    )
    if artifact is None:
        raise _error("artifact_not_found", "Artifact was not found", 404)
    return artifact


@router.get("/{job_id}/artifact-files/{artifact_id}")
async def download_artifact_file(
    job_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    disposition: Literal["attachment", "inline"] = Query(default="attachment"),
) -> Response:
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.id == artifact_id,
            Artifact.job_id == job_id,
            Artifact.subdocument_id.is_(None),
        )
    )
    if artifact is None:
        raise _error("artifact_not_found", "Artifact was not found", 404)
    filename = Path(artifact.relative_path).name
    return Response(
        content=store.read(artifact.relative_path),
        media_type=artifact.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/{job_id}/artifacts/{artifact_type}")
async def download_artifact(
    job_id: str,
    artifact_type: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    disposition: Literal["attachment", "inline"] = Query(default="attachment"),
) -> Response:
    artifact = await _artifact_or_404(db, job_id, artifact_type)
    filename = Path(artifact.relative_path).name
    return Response(
        content=store.read(artifact.relative_path),
        media_type=artifact.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/{job_id}/figures/{region_id}")
async def download_figure(
    job_id: str,
    region_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    disposition: Literal["attachment", "inline"] = Query(default="attachment"),
) -> Response:
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.type == ArtifactType.FIGURE,
            Artifact.region_id == region_id,
        )
    )
    if artifact is None:
        raise _error("artifact_not_found", "Figure was not found", 404)
    filename = Path(artifact.relative_path).name
    return Response(
        content=store.read(artifact.relative_path),
        media_type=artifact.mime_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@router.get("/{job_id}/events")
async def parse_job_events(
    request: Request, job_id: str, db: AsyncSession = Depends(get_db)
) -> StreamingResponse:
    await _job_or_404(db, job_id)
    terminal = {
        JobStatus.CANCELLED,
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.FAILED,
        JobStatus.PAUSED,
    }

    async def events():
        for _ in range(SSE_MAX_ITERATIONS):
            if await request.is_disconnected():
                return
            async with db.begin_nested():
                job = await _job_or_404(db, job_id)
                payload = _serialize(job).model_dump(mode="json")
            yield f"event: snapshot\ndata: {json.dumps(payload)}\n\n"
            if job.status in terminal:
                return
            await asyncio.sleep(0.75)
            db.expire_all()

    return StreamingResponse(events(), media_type="text/event-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parse_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> Response:
    job = await _job_or_404(db, job_id)
    if job.status in {JobStatus.PROCESSING, JobStatus.ASSEMBLING, JobStatus.CANCELLING}:
        raise _error("invalid_state", "Cancel the active job before deleting it", 409)
    try:
        store.delete_tree(f"jobs/{job_id}")
    except Exception:
        logger.exception("parse_job.storage_delete_failed", extra={"job_id": job_id})
        raise _error("storage_delete_failed", "Job files could not be deleted", 500) from None
    await db.delete(job)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
