"""Request and inspect automatic page or region reprocessing runs."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_api_key
from app.database import get_db
from app.models.db_models import ReprocessRun
from app.models.enums import JobStatus, PageStatus
from app.routers.parse_jobs import _error, _job_or_404, get_job_queue, get_object_store
from app.services.jobs import ParseJobQueue
from app.services.parsing.inspection import load_page_layout
from app.services.parsing.storage import ObjectStore

router = APIRouter(
    prefix="/api/parse-jobs",
    tags=["reprocessing"],
    dependencies=[Depends(require_api_key)],
)


class ReprocessRequest(BaseModel):
    target_kind: Literal["page", "region"]
    page_number: int = Field(ge=1)
    region_id: str | None = Field(default=None, max_length=40)
    dpi: Literal[150, 200, 300] = 300
    crop_padding: float = 0.1

    @model_validator(mode="after")
    def validate_target(self):
        if self.target_kind == "region" and not self.region_id:
            raise ValueError("region_id is required for region reprocessing")
        if self.target_kind == "page" and self.region_id:
            raise ValueError("region_id is not valid for page reprocessing")
        if self.crop_padding not in {0, 0.05, 0.1, 0.2}:
            raise ValueError("crop_padding must be 0, 0.05, 0.1, or 0.2")
        return self


class ReprocessRunResponse(BaseModel):
    id: str
    job_id: str
    target_kind: str
    page_number: int
    region_id: str | None
    dpi: int
    crop_padding: float
    status: str
    previous_fingerprint: str | None
    result_fingerprint: str | None
    decision: dict | None
    error_message: str | None
    created_at: str | None
    completed_at: str | None


def _serialize(run: ReprocessRun) -> ReprocessRunResponse:
    return ReprocessRunResponse(
        id=run.id,
        job_id=run.job_id,
        target_kind=run.target_kind,
        page_number=run.page_number,
        region_id=run.region_id,
        dpi=run.dpi,
        crop_padding=run.crop_padding,
        status=run.status,
        previous_fingerprint=run.previous_fingerprint,
        result_fingerprint=run.result_fingerprint,
        decision=run.decision,
        error_message=run.error_message,
        created_at=run.created_at.isoformat() if run.created_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
    )


@router.post(
    "/{job_id}/reprocess",
    response_model=ReprocessRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_reprocess(
    request: Request,
    job_id: str,
    body: ReprocessRequest,
    db: AsyncSession = Depends(get_db),
    store: ObjectStore = Depends(get_object_store),
    queue: ParseJobQueue = Depends(get_job_queue),
) -> ReprocessRunResponse:
    job = await _job_or_404(db, job_id)
    if job.status not in {
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.FAILED,
    }:
        raise _error("job_busy", "Wait for the current job operation to finish", 409)
    if any(item.status in {"queued", "running"} for item in job.reprocess_runs):
        raise _error("reprocess_active", "A reprocessing run is already active", 409)
    checkpoint = next(
        (item for item in job.pages if item.page_number == body.page_number), None
    )
    if checkpoint is None:
        raise _error("page_not_found", "Page is outside the selected parse range", 404)
    if body.target_kind == "region":
        try:
            layout = load_page_layout(job, body.page_number, store)
        except (KeyError, OSError, ValueError):
            raise _error("layout_not_found", "Page layout is unavailable", 404) from None
        if not any(item.id == body.region_id for item in layout.regions):
            raise _error("region_not_found", "Region is not present on this page", 404)
        if not job.settings.get("ocr_model"):
            raise _error("model_required", "Select a local or cloud OCR repair model first")
    runtime = getattr(request.app.state, "parser_runtime", None)
    if runtime is None:
        raise _error("runtime_unavailable", "Parser runtime is unavailable", 503)
    previous_dpi = int(job.settings.get("dpi", 200))
    decision: dict[str, object] = {"previous_dpi": previous_dpi}
    backup_prefix = f"jobs/{job.id}/reprocessing/{uuid.uuid4().hex}"
    if checkpoint.layout_path:
        try:
            before_layout = store.read(checkpoint.layout_path)
            before_layout_path = f"{backup_prefix}/before-layout.json"
            store.write(before_layout_path, before_layout)
            decision["before_layout_path"] = before_layout_path
        except (KeyError, OSError):
            pass
    if checkpoint.diagnostics_path:
        try:
            before_diagnostics = store.read(checkpoint.diagnostics_path)
            before_diagnostics_path = f"{backup_prefix}/before-diagnostics.json"
            store.write(before_diagnostics_path, before_diagnostics)
            decision["before_diagnostics_path"] = before_diagnostics_path
        except (KeyError, OSError):
            pass
    run = ReprocessRun(
        id=uuid.uuid4().hex,
        job_id=job.id,
        target_kind=body.target_kind,
        page_number=body.page_number,
        region_id=body.region_id,
        dpi=body.dpi,
        crop_padding=body.crop_padding,
        previous_fingerprint=checkpoint.fingerprint,
        decision=decision,
    )
    job.reprocess_runs.append(run)
    job.status = JobStatus.QUEUED
    job.cancel_requested = False
    job.error_code = None
    job.error_message = None
    job.completed_at = None
    job.settings = {**job.settings, "dpi": body.dpi}
    if body.target_kind == "page":
        checkpoint.status = PageStatus.PENDING
        checkpoint.error_code = None
        checkpoint.error_message = None
    await db.commit()
    await queue.submit(job.id)
    return _serialize(run)


@router.get(
    "/{job_id}/reprocess-runs/{run_id}", response_model=ReprocessRunResponse
)
async def get_reprocess_run(
    job_id: str, run_id: str, db: AsyncSession = Depends(get_db)
) -> ReprocessRunResponse:
    job = await _job_or_404(db, job_id)
    run = next((item for item in job.reprocess_runs if item.id == run_id), None)
    if run is None:
        raise _error("reprocess_not_found", "Reprocessing run was not found", 404)
    return _serialize(run)
