"""Local DPT-style Parse and Extract API."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.config import settings as app_settings
from app.database import get_db
from app.models.db_models import Artifact, PageCheckpoint, ParseJob
from app.models.enums import JobStatus, PageStatus
from app.rate_limit import require_rate_limit
from app.services.agentic.contracts import ExtractionResponse, ParseMetadata, ParseResponse
from app.services.agentic.extraction import (
    AgenticSchemaExtractor,
    ExtractionServiceError,
    InvalidExtractionSchemaError,
    StrictSchemaViolationError,
)
from app.services.parsing.ingest import DocumentInputError, inspect_document
from app.services.parsing.storage import FileStore
from app.services.v2_jobs import get_v2_job_queue

API_FAMILY = "agentic_v2"
ModelAlias = Literal[
    "paperplane-ade-fast-latest",
    "paperplane-ade-latest",
    "paperplane-ade-audit-latest",
]
MODEL_TO_MODE: dict[ModelAlias, str] = {
    "paperplane-ade-fast-latest": "economy",
    "paperplane-ade-latest": "balanced",
    "paperplane-ade-audit-latest": "audit",
}

router = APIRouter(
    prefix="/v2",
    tags=["agentic-v2"],
    dependencies=[Depends(require_api_key), Depends(require_rate_limit)],
)


class ArtifactResponse(BaseModel):
    id: str
    type: str
    mime_type: str
    size: int
    sha256: str
    download_url: str
    preview_url: str | None = None


class ParseJobResponse(BaseModel):
    id: str
    status: str
    model: ModelAlias
    original_filename: str
    source_mime: str
    source_size: int
    source_sha256: str
    page_count: int
    completed_pages: int
    failed_pages: int
    settings: dict[str, ModelAlias]
    models: dict[str, str]
    usage: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    source_preview_url: str
    artifacts: list[ArtifactResponse] = Field(default_factory=list)
    result: dict[str, Any] | None = None


class ParseJobListResponse(BaseModel):
    items: list[ParseJobResponse]
    page: int
    page_size: int
    total: int


class ExtractRequest(BaseModel):
    markdown: str
    json_schema: dict[str, Any]
    strict: bool = False
    model: ModelAlias = "paperplane-ade-latest"


class ExtractJobResponse(BaseModel):
    id: str
    status: Literal["queued", "completed", "failed"]
    model: ModelAlias
    result: dict[str, Any] | None = None
    error: dict[str, str] | None = None


def _error(code: str, message: str, status_code: int = 422) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def get_agentic_extractor() -> AgenticSchemaExtractor:
    """Production seam for a configured Terra caller.

    The deterministic extraction service is available, but the provider caller is injected by
    the application deployment so this route never fabricates extraction data.
    """

    raise _error(
        "extraction_service_unavailable",
        "A Terra extraction provider has not been configured",
        503,
    )


def _extraction_dependency() -> AgenticSchemaExtractor:
    return get_agentic_extractor()


def _extract_job_path(job_id: str) -> str:
    return f"extract-jobs/{job_id}.json"


def _write_extract_job(payload: dict[str, Any]) -> None:
    FileStore(app_settings.artifacts_path).write(
        _extract_job_path(payload["id"]), json.dumps(payload).encode()
    )


async def _process_extract_job(
    job_id: str, request: ExtractRequest, extractor: AgenticSchemaExtractor
) -> None:
    payload: dict[str, Any] = {
        "id": job_id,
        "status": "failed",
        "model": request.model,
        "result": None,
        "error": None,
    }
    try:
        result = await extractor.extract(
            markdown=request.markdown,
            schema=request.json_schema,
            strict=request.strict,
        )
        response = ExtractionResponse(
            extraction=result.extraction,
            extraction_metadata=result.extraction_metadata,
            markdown=request.markdown,
            metadata=ParseMetadata(
                job_id=job_id,
                model=request.model,
                page_count=max(1, request.markdown.count("<!-- page_number=")),
                output_characters=len(request.markdown),
                service_tier="local",
                total_credits=0,
            ),
            warnings=result.warnings,
            schema_violation_error=result.schema_violation_error,
        )
        payload["status"] = "completed"
        payload["result"] = response.model_dump(mode="json")
    except ExtractionServiceError as exc:
        payload["error"] = {"code": "extraction_failed", "message": str(exc)}
    except Exception as exc:  # background boundary: persist a safe terminal state
        payload["error"] = {"code": "extraction_failed", "message": type(exc).__name__}
    await asyncio.to_thread(_write_extract_job, payload)


def _is_agentic_job(job: ParseJob) -> bool:
    return job.settings.get("api_family") == API_FAMILY


def _model_for(job: ParseJob) -> ModelAlias:
    value = job.settings.get("model", "paperplane-ade-latest")
    if value not in MODEL_TO_MODE:
        return "paperplane-ade-latest"
    return value


def _serialize_job(job: ParseJob, *, result: dict[str, Any] | None = None) -> ParseJobResponse:
    artifacts = [
        ArtifactResponse(
            id=item.id,
            type=item.type,
            mime_type=item.mime_type,
            size=item.size,
            sha256=item.sha256,
            download_url=f"/v2/parse/jobs/{job.id}/artifacts/{item.id}",
            preview_url=(
                f"/v2/parse/jobs/{job.id}/artifacts/{item.id}?disposition=inline"
                if item.mime_type == "application/pdf"
                else None
            ),
        )
        for item in job.artifacts
    ]
    return ParseJobResponse(
        id=job.id,
        status=str(job.status),
        model=_model_for(job),
        original_filename=job.original_filename,
        source_mime=job.source_mime,
        source_size=job.source_size,
        source_sha256=job.source_sha256,
        page_count=job.page_count,
        completed_pages=job.completed_pages,
        failed_pages=job.failed_pages,
        settings={"model": _model_for(job)},
        models={"parser": "gpt-5.6-luna", "critic": "gpt-5.6-terra"},
        usage=(job.quality_policy_snapshot or {}).get("usage"),
        error_code=job.error_code,
        error_message=job.error_message,
        source_preview_url=f"/v2/parse/jobs/{job.id}/source",
        artifacts=artifacts,
        result=result,
    )


async def _load_job(db: AsyncSession, job_id: str) -> ParseJob:
    job = await db.scalar(
        select(ParseJob)
        .where(ParseJob.id == job_id)
        .options(
            selectinload(ParseJob.pages),
            selectinload(ParseJob.artifacts),
            selectinload(ParseJob.review_cases),
        )
    )
    if job is None or not _is_agentic_job(job):
        raise _error("job_not_found", "Job was not found", 404)
    return job


async def _reload_job(db: AsyncSession, job_id: str) -> ParseJob:
    db.expire_all()
    return await _load_job(db, job_id)


def _read_parse_result(job: ParseJob) -> ParseResponse | None:
    artifact = next((item for item in reversed(job.artifacts) if item.type == "json"), None)
    if artifact is None:
        return None
    try:
        return ParseResponse.model_validate_json(
            FileStore(app_settings.artifacts_path).read(artifact.relative_path)
        )
    except (KeyError, OSError, ValueError):
        return None


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > app_settings.max_upload_bytes:
            raise _error("too_large", "Document exceeds the upload limit", 413)
        chunks.append(chunk)
    return b"".join(chunks), Path(file.filename or "document").name


async def _create_parse_job(*, file: UploadFile, model: ModelAlias, db: AsyncSession) -> ParseJob:
    if not app_settings.openai_api_key:
        raise _error("openai_not_configured", "OPENAI_API_KEY is required for parsing", 503)
    data, filename = await _read_upload(file)
    try:
        inspected = inspect_document(
            data, filename, app_settings.max_upload_bytes, app_settings.max_document_pages
        )
    except DocumentInputError as exc:
        raise _error(exc.code, str(exc)) from exc

    job_id = uuid.uuid4().hex
    source_path = f"jobs-v2/{job_id}/source{Path(filename).suffix.lower()}"
    FileStore(app_settings.artifacts_path).write(source_path, data)
    job = ParseJob(
        id=job_id,
        original_filename=filename,
        source_path=source_path,
        source_mime=inspected.mime_type,
        source_size=len(data),
        source_sha256=hashlib.sha256(data).hexdigest(),
        page_count=inspected.page_count,
        status=JobStatus.QUEUED,
        settings={
            "api_family": API_FAMILY,
            "model": model,
            "mode": MODEL_TO_MODE[model],
            "segment_documents": False,
        },
        model_name="gpt-5.6-luna",
        review_model_name="gpt-5.6-terra",
        pages=[
            PageCheckpoint(page_number=page, status=PageStatus.PENDING)
            for page in range(1, inspected.page_count + 1)
        ],
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    await get_v2_job_queue().submit(job_id)
    return job


@router.post("/parse/jobs", response_model=ParseJobResponse, status_code=202)
async def create_parse_job(
    file: Annotated[UploadFile, File()],
    model: Annotated[ModelAlias, Form()] = "paperplane-ade-latest",
    db: AsyncSession = Depends(get_db),
) -> ParseJobResponse:
    return _serialize_job(await _create_parse_job(file=file, model=model, db=db))


@router.get("/parse/jobs", response_model=ParseJobListResponse)
async def list_parse_jobs(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
) -> ParseJobListResponse:
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
    jobs = [job for job in jobs if _is_agentic_job(job)]
    start = (page - 1) * page_size
    return ParseJobListResponse(
        items=[_serialize_job(job) for job in jobs[start : start + page_size]],
        page=page,
        page_size=page_size,
        total=len(jobs),
    )


@router.get("/parse/jobs/{job_id}", response_model=ParseJobResponse)
async def get_parse_job(job_id: str, db: AsyncSession = Depends(get_db)) -> ParseJobResponse:
    job = await _load_job(db, job_id)
    result = _read_parse_result(job)
    return _serialize_job(
        job, result=result.model_dump(mode="json") if result is not None else None
    )


@router.post("/parse/jobs/{job_id}/cancel", response_model=ParseJobResponse)
async def cancel_parse_job(job_id: str, db: AsyncSession = Depends(get_db)) -> ParseJobResponse:
    job = await _load_job(db, job_id)
    if job.status == JobStatus.QUEUED:
        result = await db.execute(
            update(ParseJob)
            .where(ParseJob.id == job_id, ParseJob.status == JobStatus.QUEUED)
            .values(status=JobStatus.CANCELLED)
        )
    elif job.status in {JobStatus.INSPECTING, JobStatus.PROCESSING, JobStatus.ASSEMBLING}:
        result = await db.execute(
            update(ParseJob)
            .where(
                ParseJob.id == job_id,
                ParseJob.status.in_(
                    [JobStatus.INSPECTING, JobStatus.PROCESSING, JobStatus.ASSEMBLING]
                ),
            )
            .values(cancel_requested=True, status=JobStatus.CANCELLING)
        )
    else:
        raise _error("invalid_state", f"Cannot cancel a job in {job.status} state", 409)
    await db.commit()
    if result.rowcount != 1:
        raise _error("invalid_state", "Job state changed concurrently — refresh and retry", 409)
    await db.refresh(job)
    return _serialize_job(job)


@router.get("/parse/jobs/{job_id}/source")
async def get_parse_source(job_id: str, db: AsyncSession = Depends(get_db)) -> Response:
    job = await _load_job(db, job_id)
    return Response(
        content=FileStore(app_settings.artifacts_path).read(job.source_path),
        media_type=job.source_mime,
        headers={"Content-Disposition": f'inline; filename="{Path(job.original_filename).name}"'},
    )


@router.get("/parse/jobs/{job_id}/artifacts/{artifact_id}")
async def get_parse_artifact(
    job_id: str,
    artifact_id: str,
    disposition: Literal["attachment", "inline"] = Query(default="attachment"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _load_job(db, job_id)
    artifact = await db.scalar(
        select(Artifact).where(Artifact.id == artifact_id, Artifact.job_id == job_id)
    )
    if artifact is None:
        raise _error("artifact_not_found", "Artifact was not found", 404)
    return Response(
        content=FileStore(app_settings.artifacts_path).read(artifact.relative_path),
        media_type=artifact.mime_type,
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{Path(artifact.relative_path).name}"'
            )
        },
    )


@router.get("/parse/jobs/{job_id}/trace")
async def get_parse_trace(job_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = await _load_job(db, job_id)
    return {"items": (job.quality_policy_snapshot or {}).get("agent_trace", [])}


@router.get("/parse/jobs/{job_id}/reviews")
async def get_parse_reviews(job_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    job = await _load_job(db, job_id)
    return {
        "items": [
            {
                "id": item.id,
                "page_number": item.page_number,
                "item_kind": item.item_kind,
                "item_key": item.item_key,
                "severity": item.severity,
                "status": item.status,
                "failure_codes": item.failure_codes,
            }
            for item in job.review_cases
        ]
    }


@router.post("/parse", response_model=ParseResponse)
async def parse_document(
    file: Annotated[UploadFile, File()],
    model: Annotated[ModelAlias, Form()] = "paperplane-ade-latest",
    db: AsyncSession = Depends(get_db),
) -> Response:
    job = await _create_parse_job(file=file, model=model, db=db)
    deadline = time.monotonic() + app_settings.job_timeout_seconds
    terminal = {
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
    while job.status not in terminal and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
        job = await _reload_job(db, job.id)
    if job.status not in terminal:
        raise _error("parse_timeout", "Synchronous parsing timed out", 504)
    if job.status == JobStatus.FAILED or job.failed_pages >= job.page_count:
        raise _error(job.error_code or "parse_failed", job.error_message or "Parsing failed", 500)

    result = _read_parse_result(job)
    if result is None:
        raise _error("parse_result_unavailable", "Completed parse result is unavailable", 500)
    status_code = 206 if job.failed_pages else 200
    return JSONResponse(content=result.model_dump(mode="json"), status_code=status_code)


@router.post("/extract", response_model=ExtractionResponse)
async def extract_document(
    request: ExtractRequest,
    extractor: AgenticSchemaExtractor = Depends(_extraction_dependency),
) -> Response:
    try:
        result = await extractor.extract(
            markdown=request.markdown,
            schema=request.json_schema,
            strict=request.strict,
        )
    except StrictSchemaViolationError as exc:
        raise _error("schema_violation", str(exc), 422) from exc
    except InvalidExtractionSchemaError as exc:
        raise _error("invalid_schema", str(exc), 422) from exc
    except ExtractionServiceError as exc:
        raise _error("invalid_extraction", str(exc), exc.status_code) from exc

    response = ExtractionResponse(
        extraction=result.extraction,
        extraction_metadata=result.extraction_metadata,
        markdown=request.markdown,
        metadata=ParseMetadata(
            job_id=uuid.uuid4().hex,
            model=request.model,
            page_count=max(1, request.markdown.count("<!-- page_number=")),
            output_characters=len(request.markdown),
            service_tier="local",
            total_credits=0,
        ),
        warnings=result.warnings,
        schema_violation_error=result.schema_violation_error,
    )
    return JSONResponse(
        content=response.model_dump(mode="json"),
        status_code=206 if result.schema_violation_error else 200,
    )


@router.post("/extract/jobs", response_model=ExtractJobResponse, status_code=202)
async def create_extract_job(
    request: ExtractRequest,
    background_tasks: BackgroundTasks,
    extractor: AgenticSchemaExtractor = Depends(_extraction_dependency),
) -> ExtractJobResponse:
    job_id = uuid.uuid4().hex
    queued = ExtractJobResponse(id=job_id, status="queued", model=request.model)
    _write_extract_job(queued.model_dump(mode="json"))
    background_tasks.add_task(_process_extract_job, job_id, request, extractor)
    return queued


@router.get("/extract/jobs/{job_id}", response_model=ExtractJobResponse)
async def get_extract_job(job_id: str) -> ExtractJobResponse:
    try:
        payload = json.loads(FileStore(app_settings.artifacts_path).read(_extract_job_path(job_id)))
    except (FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        raise _error("extract_job_not_found", "Extraction job was not found", 404) from exc
    return ExtractJobResponse.model_validate(payload)


__all__ = ["API_FAMILY", "ModelAlias", "router"]
