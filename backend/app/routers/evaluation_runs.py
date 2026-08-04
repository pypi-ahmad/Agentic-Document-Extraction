"""Grounded-document evaluation run API."""

from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Annotated, Any
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import require_api_key
from app.config import settings
from app.database import async_session, get_db
from app.models.db_models import EvaluationCase, EvaluationRun, PageCheckpoint, ParseJob
from app.models.enums import JobStatus, PageStatus
from app.models.schemas import ParseSettings
from app.services.evaluation import GroundTruthDocument
from app.services.evaluation_runtime import finalize_evaluations_for_job
from app.services.jobs import ParseJobQueue, get_job_queue
from app.services.parsing.ingest import DocumentInputError, inspect_document
from app.services.parsing.model_catalog import OllamaCatalogUnavailable
from app.services.parsing.storage import FileStore, ObjectStore
from app.services.parsing.vision_providers import ProviderError

router = APIRouter(
    prefix="/api/evaluation-runs",
    tags=["evaluation-runs"],
    dependencies=[Depends(require_api_key)],
)


class EvaluationCaseResponse(BaseModel):
    id: str
    external_id: str
    parse_job_id: str
    status: str
    metrics: dict[str, float] | None = None
    error_message: str | None = None
    report_url: str | None = None


class EvaluationRunResponse(BaseModel):
    id: str
    kind: str
    status: str
    settings: dict[str, Any]
    metrics: dict[str, float] | None = None
    total_cases: int
    completed_cases: int
    failed_cases: int
    error_message: str | None = None
    report_url: str | None = None
    cases: list[EvaluationCaseResponse] = Field(default_factory=list)


class EvaluationRunListResponse(BaseModel):
    items: list[EvaluationRunResponse]
    total: int


class DatasetCase(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    source: str
    labels: str


class DatasetManifest(BaseModel):
    schema_version: str
    cases: list[DatasetCase] = Field(min_length=1, max_length=100)


def get_object_store() -> ObjectStore:
    return FileStore(settings.artifacts_path)


def _error(code: str, message: str, status_code: int) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _serialize(run: EvaluationRun) -> EvaluationRunResponse:
    return EvaluationRunResponse(
        id=run.id,
        kind=run.kind,
        status=run.status,
        settings=run.settings,
        metrics=run.metrics,
        total_cases=run.total_cases,
        completed_cases=run.completed_cases,
        failed_cases=run.failed_cases,
        error_message=run.error_message,
        report_url=f"/api/evaluation-runs/{run.id}/report" if run.report_path else None,
        cases=[
            EvaluationCaseResponse(
                id=case.id,
                external_id=case.external_id,
                parse_job_id=case.parse_job_id,
                status=case.status,
                metrics=case.metrics,
                error_message=case.error_message,
                report_url=(
                    f"/api/evaluation-runs/{run.id}/cases/{case.id}/report"
                    if case.report_path
                    else None
                ),
            )
            for case in run.cases
        ],
    )


async def _run_or_404(db: AsyncSession, run_id: str) -> EvaluationRun:
    run = (
        await db.execute(
            select(EvaluationRun)
            .where(EvaluationRun.id == run_id)
            .options(selectinload(EvaluationRun.cases))
        )
    ).scalar_one_or_none()
    if run is None:
        raise _error("evaluation_not_found", "Evaluation run was not found", 404)
    return run


@router.post("/from-job/{job_id}", response_model=EvaluationRunResponse, status_code=201)
async def evaluate_completed_job(
    job_id: str,
    gold: Annotated[UploadFile, File()],
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> EvaluationRunResponse:
    job = await db.get(ParseJob, job_id)
    if job is None:
        raise _error("job_not_found", "Parse job was not found", 404)
    if job.status not in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}:
        raise _error("job_not_complete", "Only completed parse jobs can be evaluated", 409)
    data = await gold.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise _error("labels_too_large", "Ground-truth JSON exceeds 10 MB", 413)
    try:
        labels = GroundTruthDocument.model_validate_json(data)
    except ValueError as exc:
        raise _error("invalid_ground_truth", str(exc), 422) from exc
    if labels.source_sha256 and labels.source_sha256 != job.source_sha256:
        raise _error("source_hash_mismatch", "Ground truth belongs to a different document", 422)
    run_id, case_id = uuid.uuid4().hex, uuid.uuid4().hex
    gold_path = f"evaluations/{run_id}/labels/{case_id}.json"
    store.write(gold_path, data)
    run = EvaluationRun(
        id=run_id,
        kind="single",
        status="running",
        settings=job.settings,
        total_cases=1,
        cases=[
            EvaluationCase(
                id=case_id,
                external_id=labels.document_id,
                parse_job_id=job.id,
                source_sha256=job.source_sha256,
                gold_path=gold_path,
            )
        ],
    )
    db.add(run)
    await db.commit()
    await finalize_evaluations_for_job(async_session, store, job.id)
    db.expire_all()
    return _serialize(await _run_or_404(db, run_id))


@router.post("", response_model=EvaluationRunResponse, status_code=202)
async def create_batch_evaluation(
    request: Request,
    dataset: Annotated[UploadFile, File()],
    settings_json: Annotated[str, Form(alias="settings")] = "{}",
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    queue: ParseJobQueue = Depends(get_job_queue),
) -> EvaluationRunResponse:
    try:
        parse_settings = ParseSettings.model_validate_json(settings_json or "{}")
    except ValueError as exc:
        raise _error("invalid_settings", str(exc), 422) from exc
    await _validate_models(request, parse_settings)
    archive_limit = min(settings.max_upload_bytes * 3, 500 * 1024 * 1024)
    archive = await dataset.read(archive_limit + 1)
    if len(archive) > archive_limit:
        raise _error("dataset_too_large", "Evaluation dataset archive is too large", 413)
    prepared = _prepare_dataset(archive, parse_settings)
    if queue.in_flight + len(prepared) > settings.job_queue_max_depth:
        raise _error("queue_full", "The evaluation dataset exceeds available queue capacity", 503)
    run_id = uuid.uuid4().hex
    run = EvaluationRun(
        id=run_id,
        kind="batch",
        status="running",
        settings=parse_settings.model_dump(mode="json"),
        total_cases=len(prepared),
    )
    jobs: list[ParseJob] = []
    for item in prepared:
        job_id, case_id = uuid.uuid4().hex, uuid.uuid4().hex
        suffix = Path(item["filename"]).suffix.lower()
        source_path = f"jobs/{job_id}/source{suffix}"
        gold_path = f"evaluations/{run_id}/labels/{case_id}.json"
        store.write(source_path, item["source"])
        store.write(gold_path, item["gold"])
        inspected = item["inspected"]
        end_page = parse_settings.end_page or inspected.page_count
        job = ParseJob(
            id=job_id,
            original_filename=Path(item["filename"]).name,
            source_path=source_path,
            source_mime=inspected.mime_type,
            source_size=len(item["source"]),
            source_sha256=item["sha256"],
            page_count=inspected.page_count,
            status=JobStatus.QUEUED,
            settings=parse_settings.model_dump(mode="json"),
            model_name="native-text",
            review_model_name=parse_settings.review_model,
            pages=[
                PageCheckpoint(page_number=page, status=PageStatus.PENDING)
                for page in range(parse_settings.start_page, end_page + 1)
            ],
        )
        jobs.append(job)
        run.cases.append(
            EvaluationCase(
                id=case_id,
                external_id=item["id"],
                parse_job_id=job_id,
                source_sha256=item["sha256"],
                gold_path=gold_path,
            )
        )
    db.add_all([*jobs, run])
    await db.commit()
    for job in jobs:
        await queue.submit(job.id)
    return _serialize(await _run_or_404(db, run_id))


async def _validate_models(request: Request, parse_settings: ParseSettings) -> None:
    runtime = getattr(request.app.state, "parser_runtime", None)
    if runtime is None:
        raise _error("runtime_unavailable", "Parser runtime is unavailable", 503)
    try:
        if parse_settings.ocr_model:
            await runtime.provider_registry.validate_selection(
                parse_settings.ocr_provider, parse_settings.ocr_model
            )
        if parse_settings.cloud_mode != "off" and parse_settings.review_model:
            if parse_settings.review_provider == "ollama":
                await runtime.model_catalog.require_compatible(parse_settings.review_model)
            else:
                await runtime.provider_registry.validate_selection(
                    parse_settings.review_provider, parse_settings.review_model
                )
    except OllamaCatalogUnavailable as exc:
        raise _error("ollama_unavailable", str(exc), 503) from exc
    except (ProviderError, ValueError) as exc:
        raise _error("model_not_available", str(exc), 422) from exc


def _prepare_dataset(archive: bytes, parse_settings: ParseSettings) -> list[dict[str, Any]]:
    try:
        with ZipFile(BytesIO(archive)) as bundle:
            members = {item.filename: item for item in bundle.infolist() if not item.is_dir()}
            for name in members:
                path = PurePosixPath(name.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("dataset archive contains an unsafe path")
            if sum(item.file_size for item in members.values()) > 2 * 1024 * 1024 * 1024:
                raise ValueError("dataset archive expands beyond 2 GB")
            manifest_info = members.get("manifest.json")
            if manifest_info is None:
                raise ValueError("dataset archive must contain manifest.json")
            manifest = DatasetManifest.model_validate_json(bundle.read(manifest_info))
            if manifest.schema_version not in {
                "paperplane-eval-dataset/v1",
                "paperplane-eval-dataset/v2",
            }:
                raise ValueError("unsupported evaluation dataset schema")
            if len({case.id for case in manifest.cases}) != len(manifest.cases):
                raise ValueError("dataset case IDs must be unique")
            prepared: list[dict[str, Any]] = []
            for case in manifest.cases:
                if case.source not in members or case.labels not in members:
                    raise ValueError(f"dataset case {case.id} references a missing file")
                source = bundle.read(members[case.source])
                if len(source) > settings.max_upload_bytes:
                    raise ValueError(f"dataset case {case.id} exceeds the document size limit")
                filename = Path(PurePosixPath(case.source).name).name
                inspected = inspect_document(
                    source, filename, settings.max_upload_bytes, settings.max_document_pages
                )
                if parse_settings.end_page and parse_settings.end_page > inspected.page_count:
                    raise ValueError(f"dataset case {case.id} has an invalid page range")
                gold_data = bundle.read(members[case.labels])
                gold = GroundTruthDocument.model_validate_json(gold_data)
                digest = hashlib.sha256(source).hexdigest()
                if gold.document_id != case.id:
                    raise ValueError(f"dataset case {case.id} does not match its gold document_id")
                if gold.source_sha256 and gold.source_sha256 != digest:
                    raise ValueError(f"dataset case {case.id} has a source hash mismatch")
                prepared.append(
                    {
                        "id": case.id,
                        "filename": filename,
                        "source": source,
                        "gold": gold_data,
                        "sha256": digest,
                        "inspected": inspected,
                    }
                )
            return prepared
    except (BadZipFile, DocumentInputError, KeyError, OSError, ValueError) as exc:
        raise _error("invalid_dataset", str(exc), 422) from exc


@router.get("", response_model=EvaluationRunListResponse)
async def list_evaluation_runs(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
) -> EvaluationRunListResponse:
    total = int(await db.scalar(select(func.count(EvaluationRun.id))) or 0)
    runs = list(
        (
            await db.execute(
                select(EvaluationRun)
                .options(selectinload(EvaluationRun.cases))
                .order_by(EvaluationRun.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .unique()
    )
    return EvaluationRunListResponse(items=[_serialize(run) for run in runs], total=total)


@router.get("/{run_id}", response_model=EvaluationRunResponse)
async def get_evaluation_run(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> EvaluationRunResponse:
    return _serialize(await _run_or_404(db, run_id))


@router.post("/{run_id}/cancel", response_model=EvaluationRunResponse)
async def cancel_evaluation_run(
    run_id: str, db: AsyncSession = Depends(get_db)
) -> EvaluationRunResponse:
    run = await _run_or_404(db, run_id)
    if run.status not in {"pending", "running"}:
        raise _error("invalid_state", f"Cannot cancel an evaluation in {run.status} state", 409)
    for case in run.cases:
        if case.status != "pending":
            continue
        job = await db.get(ParseJob, case.parse_job_id)
        if job is not None and job.status == JobStatus.QUEUED:
            job.status = JobStatus.CANCELLED
        elif job is not None and job.status in {
            JobStatus.INSPECTING,
            JobStatus.PROCESSING,
            JobStatus.ASSEMBLING,
        }:
            job.cancel_requested = True
            job.status = JobStatus.CANCELLING
        case.status = "failed"
        case.error_message = "Evaluation cancelled"
    run.status = "cancelled"
    run.failed_cases = sum(case.status == "failed" for case in run.cases)
    await db.commit()
    return _serialize(run)


@router.get("/{run_id}/report")
async def get_evaluation_report(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> Response:
    run = await _run_or_404(db, run_id)
    if not run.report_path:
        raise _error("report_not_ready", "Evaluation report is not ready", 409)
    return Response(
        store.read(run.report_path),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="evaluation-{run.id}.json"'},
    )


@router.get("/{run_id}/cases/{case_id}/report")
async def get_case_report(
    run_id: str,
    case_id: str,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
) -> Response:
    run = await _run_or_404(db, run_id)
    case = next((item for item in run.cases if item.id == case_id), None)
    if case is None or not case.report_path:
        raise _error("report_not_ready", "Evaluation case report is not ready", 409)
    return Response(
        store.read(case.report_path),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="evaluation-{case.id}.json"'},
    )
