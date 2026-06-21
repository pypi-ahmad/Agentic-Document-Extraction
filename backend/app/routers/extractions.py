"""Extraction job endpoints — run and retrieve extractions."""

import asyncio
import datetime as _dt
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import (
    AUDIT_EVENT_COMPLETED,
    AUDIT_EVENT_FAILED,
    AUDIT_EVENT_NEEDS_REVIEW,
    AUDIT_EVENT_RETRIED,
    AUDIT_EVENT_REVIEW_SUBMITTED,
    AUDIT_EVENT_STARTED,
    JOB_TIMEOUT_S,
    NO_STORE_HEADERS,
    SSE_KEEPALIVE_S,
    SSE_MAX_ITERATIONS,
    SSE_TERMINAL_STATUSES,
)
from app.database import async_session, get_db
from app.logging_setup import get_logger as _get_logger
from app.metrics import metrics as _metrics
from app.models.db_models import (
    Document,
    Extraction,
    ExtractionReview,
    ExtractionSchema,
    ExtractionStep,
)
from app.models.schemas import (
    ExtractionCreate,
    ExtractionResponse,
    ExtractionResultResponse,
    ExtractionStepResponse,
    ExtractionValidationResponse,
    ReviewCreate,
    ReviewResponse,
)
from app.services.audit import record_audit_event
from app.utils.datetime import duration_ms as _duration_ms
from app.utils.http import apply_no_store as _apply_no_store_headers

router = APIRouter(prefix="/api/extractions", tags=["Extractions"])
_log = _get_logger("app.extractions")

logger = logging.getLogger(__name__)

# Maximum wall-clock time for a single extraction job (seconds).
_JOB_TIMEOUT = JOB_TIMEOUT_S
_PIPELINE_STEPS = ("parse", "extract", "validate", "finalize")


def _no_store_headers(extra_headers: dict[str, str] | None = None) -> dict[str, str]:
    if not extra_headers:
        return dict(NO_STORE_HEADERS)
    return {**NO_STORE_HEADERS, **extra_headers}


def _build_queued_response(extraction: Extraction) -> ExtractionResponse:
    """Serialize a freshly queued extraction without lazy-loading relations."""
    return ExtractionResponse(
        id=extraction.id,
        document_id=extraction.document_id,
        schema_id=extraction.schema_id,
        ocr_provider=extraction.ocr_provider,
        llm_provider=extraction.llm_provider,
        llm_model=extraction.llm_model,
        status=extraction.status,
        ocr_text=extraction.ocr_text,
        result=extraction.result,
        validation_errors=extraction.validation_errors,
        validation_results=extraction.validation_results,
        review_verdict=extraction.review_verdict,
        error=extraction.error,
        ocr_provider_used=extraction.ocr_provider_used,
        llm_provider_used=extraction.llm_provider_used,
        llm_model_used=extraction.llm_model_used,
        confidence=extraction.confidence,
        extract_attempts=extraction.extract_attempts,
        error_category=extraction.error_category,
        steps=[],
        reviews=[],
        created_at=extraction.created_at,
        started_at=extraction.started_at,
        completed_at=extraction.completed_at,
        reviewed_at=extraction.reviewed_at,
    )


def _sse_step_signature(
    steps: list[ExtractionStep],
) -> tuple[tuple[str, str, str | None, int | None, str | None], ...]:
    return tuple(
        (
            step.name,
            step.status,
            step.error,
            step.duration_ms,
            step.completed_at.isoformat() if step.completed_at else None,
        )
        for step in steps
    )


def _apply_failure_state(
    extraction: Extraction,
    error_msg: str,
    *,
    error_category: str,
    finished_at: _dt.datetime | None = None,
) -> None:
    """Normalize failed extraction fields in one place."""
    finished_at = finished_at or _dt.datetime.now(_dt.UTC)
    extraction.status = "failed"
    extraction.error = error_msg
    if not extraction.completed_at:
        extraction.completed_at = finished_at
    extraction.error_category = error_category


def _finalize_failed_step(
    step: ExtractionStep,
    error_msg: str,
    *,
    finished_at: _dt.datetime | None = None,
) -> None:
    """Finalize a running step as failed with coherent timing metadata."""
    finished_at = finished_at or _dt.datetime.now(_dt.UTC)
    step.status = "failed"
    step.error = error_msg
    if not step.completed_at:
        step.completed_at = finished_at
    if step.started_at and step.duration_ms is None and step.completed_at:
        step.duration_ms = _duration_ms(step.started_at, step.completed_at)


async def _finalize_running_steps(
    db: AsyncSession,
    extraction_id: str,
    error_msg: str,
    *,
    finished_at: _dt.datetime | None = None,
) -> None:
    """Convert any lingering running steps into failed terminal rows."""
    finished_at = finished_at or _dt.datetime.now(_dt.UTC)
    result = await db.execute(
        select(ExtractionStep)
        .where(ExtractionStep.extraction_id == extraction_id)
        .where(ExtractionStep.status == "running")
    )
    for step in result.scalars():
        _finalize_failed_step(step, error_msg, finished_at=finished_at)


async def _backfill_missing_terminal_steps(
    db: AsyncSession,
    extraction_id: str,
) -> None:
    """Add skipped rows for downstream pipeline steps missing after a terminal failure."""
    result = await db.execute(
        select(ExtractionStep)
        .where(ExtractionStep.extraction_id == extraction_id)
        .order_by(ExtractionStep.id)
    )
    steps = list(result.scalars())
    if not steps:
        return

    existing_names = {step.name for step in steps}
    existing_indexes = [
        _PIPELINE_STEPS.index(step.name) for step in steps if step.name in _PIPELINE_STEPS
    ]
    if not existing_indexes:
        return

    highest_index = max(existing_indexes)
    for step_name in _PIPELINE_STEPS[highest_index + 1 :]:
        if step_name in existing_names:
            continue
        db.add(
            ExtractionStep(
                extraction_id=extraction_id,
                name=step_name,
                status="skipped",
            )
        )


async def _run_extraction_job(extraction_id: str) -> None:
    """Background task that runs the LangGraph extraction pipeline.

    Applies a wall-clock timeout so a hanging LLM call cannot block
    the worker indefinitely.  On timeout or unexpected crash the DB
    row is marked ``failed`` with a descriptive error.
    """
    try:
        await asyncio.wait_for(
            _run_extraction_pipeline(extraction_id),
            timeout=_JOB_TIMEOUT,
        )
    except TimeoutError:
        logger.error("Extraction %s timed out after %ds", extraction_id, _JOB_TIMEOUT)
        await _mark_job_failed(
            extraction_id,
            f"Job timed out after {_JOB_TIMEOUT}s. Please retry.",
        )
    except Exception:
        logger.exception("Unexpected error in extraction job %s", extraction_id)
        await _mark_job_failed(
            extraction_id,
            "An unexpected error occurred. Please retry.",
        )


async def _mark_job_failed(extraction_id: str, error_msg: str) -> None:
    """Mark an extraction as failed and clean up any stuck steps.

    Called from the outer job wrapper when the pipeline times out or
    crashes.  Sets ``completed_at`` and ``error_category`` so the
    failure is fully visible, and marks any lingering ``running``
    steps as ``failed`` so they don't stay stuck.
    """
    from app.services.extraction.error_classify import classify_error

    async with async_session() as db:
        extraction = await db.get(Extraction, extraction_id)
        if extraction and extraction.status not in ("completed", "needs_review", "failed"):
            finished_at = _dt.datetime.now(_dt.UTC)
            _apply_failure_state(
                extraction,
                error_msg,
                error_category=classify_error(error_msg, "failed") or "unknown",
                finished_at=finished_at,
            )
            await _finalize_running_steps(
                db,
                extraction_id,
                error_msg,
                finished_at=finished_at,
            )
            await _backfill_missing_terminal_steps(db, extraction_id)
            await db.commit()


async def _run_extraction_pipeline(extraction_id: str) -> None:
    """Core pipeline logic with step-level persistence.

    Uses ``astream(stream_mode="updates")`` so each LangGraph node's
    output is captured as an ``ExtractionStep`` row with timing.  The
    extraction's status is updated after every node, making intermediate
    progress visible to frontend polls.
    """
    from app.services.extraction.graph import build_initial_state, extraction_graph

    async with async_session() as db:
        extraction = await db.get(Extraction, extraction_id)
        if not extraction:
            return

        extraction.status = "processing"
        extraction.started_at = _dt.datetime.now(_dt.UTC)
        await db.commit()

        schema = await db.get(ExtractionSchema, extraction.schema_id)
        if not schema:
            _apply_failure_state(
                extraction,
                "Schema not found",
                error_category="unknown",
            )
            await db.commit()
            return

        doc = await db.get(Document, extraction.document_id)
        if not doc:
            _apply_failure_state(
                extraction,
                "Document not found",
                error_category="unknown",
            )
            await db.commit()
            return

        initial_state = build_initial_state(
            file_path=doc.file_path,
            schema_fields=schema.fields,
            ocr_provider=extraction.ocr_provider,
            llm_provider=extraction.llm_provider,
            llm_model=extraction.llm_model,
        )

        accumulated: dict = {}
        created_steps: dict[str, ExtractionStep] = {}
        step_start = _dt.datetime.now(_dt.UTC)
        pipeline_error: str | None = None

        # Create first step as "running" so SSE/polls see it immediately
        current_step = ExtractionStep(
            extraction_id=extraction_id,
            name="parse",
            status="running",
            started_at=step_start,
        )
        db.add(current_step)
        created_steps["parse"] = current_step
        await db.commit()

        try:
            async for chunk in extraction_graph.astream(
                initial_state,
                stream_mode="updates",
            ):
                node_name = next(iter(chunk))
                if node_name not in _PIPELINE_STEPS:
                    continue  # skip __start__ / __end__

                node_output = chunk[node_name]
                now = _dt.datetime.now(_dt.UTC)
                duration_ms = int((now - step_start).total_seconds() * 1000)

                accumulated.update(node_output)

                step_status = "completed"
                step_error = None
                if node_output.get("status") == "failed":
                    step_status = "failed"
                    step_error = node_output.get("error")

                # Finalise the current running step
                current_step.status = step_status
                current_step.completed_at = now
                current_step.duration_ms = duration_ms
                current_step.error = step_error

                # Update extraction status so polls see intermediate progress
                if "status" in node_output:
                    extraction.status = node_output["status"]

                # Create the next step as "running" when pipeline continues
                step_idx = _PIPELINE_STEPS.index(node_name)
                if step_status != "failed" and step_idx + 1 < len(_PIPELINE_STEPS):
                    next_name = _PIPELINE_STEPS[step_idx + 1]
                    current_step = ExtractionStep(
                        extraction_id=extraction_id,
                        name=next_name,
                        status="running",
                        started_at=now,
                    )
                    db.add(current_step)
                    created_steps[next_name] = current_step

                await db.commit()
                step_start = now
        except Exception:
            logger.exception("Pipeline error in extraction %s", extraction_id)
            pipeline_error = "Pipeline error: an internal error occurred. Please retry."
            # Mark any in-flight step as failed
            if current_step.status == "running":
                _finalize_failed_step(current_step, "Internal error")

        # Mark skipped steps (pipeline short-circuited on failure)
        for name in _PIPELINE_STEPS:
            if name not in created_steps:
                db.add(
                    ExtractionStep(
                        extraction_id=extraction_id,
                        name=name,
                        status="skipped",
                    )
                )

        # Persist final accumulated state
        if pipeline_error:
            extraction.status = "failed"
            extraction.error = pipeline_error
        else:
            extraction.ocr_text = accumulated.get("ocr_text")
            extraction.status = accumulated.get("status", "failed")
            extraction.error = accumulated.get("error") or None
            extraction.result = accumulated.get("extracted_data") or None
            extraction.validation_errors = accumulated.get("validation_errors") or None
            extraction.validation_results = accumulated.get("validation_results") or None
            extraction.review_verdict = accumulated.get("review_verdict") or None
            extraction.ocr_provider_used = accumulated.get("ocr_provider_used") or None
            extraction.llm_provider_used = accumulated.get("llm_provider_used") or None
            extraction.llm_model_used = accumulated.get("llm_model_used") or None
            extraction.confidence = accumulated.get("confidence") or None
            extraction.extract_attempts = accumulated.get("extract_attempts") or None
            completed_at = accumulated.get("completed_at")
            if completed_at:
                extraction.completed_at = _dt.datetime.fromisoformat(completed_at)

        # Ensure completed_at is set for all terminal states (including failures)
        if (
            extraction.status in ("completed", "needs_review", "failed")
            and not extraction.completed_at
        ):
            extraction.completed_at = _dt.datetime.now(_dt.UTC)

        # Classify the error for reviewer triage
        from app.services.extraction.error_classify import classify_error

        extraction.error_category = classify_error(extraction.error, extraction.status)

        # Observability: record the terminal event in metrics + audit.
        if extraction.status in ("completed", "needs_review", "failed"):
            _metrics.in_flight_jobs.dec()
            _metrics.extractions_total.labels(status=extraction.status).inc()
            if extraction.started_at and extraction.completed_at:
                _metrics.extraction_duration_seconds.observe(
                    (extraction.completed_at - extraction.started_at).total_seconds()
                )
            event = {
                "completed": AUDIT_EVENT_COMPLETED,
                "needs_review": AUDIT_EVENT_NEEDS_REVIEW,
                "failed": AUDIT_EVENT_FAILED,
            }.get(extraction.status)
            if event:
                await record_audit_event(
                    db,
                    extraction_id=extraction_id,
                    event=event,
                    payload={
                        "error_category": extraction.error_category,
                        "extract_attempts": extraction.extract_attempts,
                    },
                )

        await db.commit()


@router.post("/", response_model=ExtractionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_extraction(
    body: ExtractionCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ExtractionResponse:
    """Start a new extraction job (runs in background)."""
    _apply_no_store_headers(response)
    # Validate references
    doc = await db.get(Document, body.document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    schema = await db.get(ExtractionSchema, body.schema_id)
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found")

    extraction = Extraction(
        document_id=body.document_id,
        schema_id=body.schema_id,
        ocr_provider=body.ocr_provider,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model,
        status="queued",
        created_at=_dt.datetime.now(_dt.UTC),
    )
    db.add(extraction)
    await db.commit()

    _metrics.in_flight_jobs.inc()
    _metrics.extractions_total.labels(status="queued").inc()
    from app.services.jobs import get_job_queue

    queue = get_job_queue()
    try:
        await queue.submit(extraction.id, lambda: _run_extraction_job(extraction.id))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    await record_audit_event(
        db,
        extraction_id=extraction.id,
        event=AUDIT_EVENT_STARTED,
        payload={"schema_id": extraction.schema_id, "document_id": extraction.document_id},
    )
    await db.commit()
    return _build_queued_response(extraction)


@router.post(
    "/{extraction_id}/retry",
    response_model=ExtractionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_extraction(
    extraction_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ExtractionResponse:
    """Re-queue a failed extraction job.

    Only extractions in ``failed`` status can be retried.  The row is
    reset to ``queued`` and re-submitted to the background worker.
    """
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    if extraction.status != "failed":
        raise HTTPException(
            status_code=409,
            detail=f"Only failed extractions can be retried (current: {extraction.status})",
        )

    # Reset mutable fields so the pipeline starts clean
    extraction.status = "queued"
    extraction.error = None
    extraction.ocr_text = None
    extraction.result = None
    extraction.validation_errors = None
    extraction.validation_results = None
    extraction.review_verdict = None
    extraction.ocr_provider_used = None
    extraction.llm_provider_used = None
    extraction.llm_model_used = None
    extraction.confidence = None
    extraction.extract_attempts = None
    extraction.error_category = None
    extraction.started_at = None
    extraction.completed_at = None
    extraction.reviewed_at = None

    # Clear previous step records
    await db.execute(delete(ExtractionStep).where(ExtractionStep.extraction_id == extraction_id))
    extraction.steps = []

    # Clear prior review history so a retried run does not inherit stale
    # reviewer decisions from an earlier failed attempt on the same row.
    await db.execute(
        delete(ExtractionReview).where(ExtractionReview.extraction_id == extraction_id)
    )
    extraction.reviews = []

    await db.commit()

    _metrics.extractions_total.labels(status="retried").inc()
    from app.services.jobs import get_job_queue

    queue = get_job_queue()
    try:
        await queue.submit(extraction.id, lambda: _run_extraction_job(extraction.id))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    await record_audit_event(
        db,
        extraction_id=extraction.id,
        event=AUDIT_EVENT_RETRIED,
    )
    await db.commit()
    return _build_queued_response(extraction)


@router.get("/", response_model=list[ExtractionResponse])
async def list_extractions(
    response: Response,
    document_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Extraction]:
    """List extractions, optionally filtered by document."""
    _apply_no_store_headers(response)
    stmt = select(Extraction).order_by(Extraction.created_at.desc())
    if document_id:
        stmt = stmt.where(Extraction.document_id == document_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{extraction_id}", response_model=ExtractionResponse)
async def get_extraction(
    extraction_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> Extraction:
    """Get extraction status and results."""
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return extraction


# ── SSE live progress stream ─────────────────────────────────────────


_SSE_POLL_INTERVAL = SSE_KEEPALIVE_S
_SSE_TERMINAL = SSE_TERMINAL_STATUSES
_SSE_MAX_ITERATIONS = SSE_MAX_ITERATIONS


@router.get("/{extraction_id}/stream")
async def stream_extraction_progress(extraction_id: str) -> StreamingResponse:
    """Stream extraction progress as Server-Sent Events.

    Emits a JSON event each time the extraction status or step state
    changes.  Closes automatically when the extraction reaches a
    terminal state (completed / needs_review / failed).
    """

    async def _event_generator():
        last_status: str | None = None
        last_step_signature: (
            tuple[tuple[str, str, str | None, int | None, str | None], ...] | None
        ) = None

        for _ in range(_SSE_MAX_ITERATIONS):
            async with async_session() as db:
                extraction = await db.get(Extraction, extraction_id)
                if not extraction:
                    yield _sse_event({"error": "Extraction not found"})
                    return

                steps = extraction.steps or []
                cur_status = extraction.status
                cur_step_signature = _sse_step_signature(steps)

                # Only emit when live progress actually changed.
                if cur_status != last_status or cur_step_signature != last_step_signature:
                    payload = ExtractionResponse.model_validate(extraction)
                    yield _sse_event(payload.model_dump(mode="json"))
                    last_status = cur_status
                    last_step_signature = cur_step_signature

                if cur_status in _SSE_TERMINAL:
                    return

            await asyncio.sleep(_SSE_POLL_INTERVAL)

        # One final snapshot prevents a late status/step transition from being
        # dropped exactly when the bounded stream loop expires.
        async with async_session() as db:
            extraction = await db.get(Extraction, extraction_id)
            if not extraction:
                return

            steps = extraction.steps or []
            cur_status = extraction.status
            cur_step_signature = _sse_step_signature(steps)

            if cur_status != last_status or cur_step_signature != last_step_signature:
                payload = ExtractionResponse.model_validate(extraction)
                yield _sse_event(payload.model_dump(mode="json"))

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers=_no_store_headers({"X-Accel-Buffering": "no"}),
    )


def _sse_event(data: dict) -> str:
    """Format a dict as a single SSE ``data:`` frame."""
    return f"data: {json.dumps(data, default=str)}\n\n"


@router.get("/{extraction_id}/result", response_model=ExtractionResultResponse)
async def get_extraction_result(
    extraction_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ExtractionResultResponse:
    """Get only the extraction result data."""
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return ExtractionResultResponse(
        extraction_id=extraction.id,
        status=extraction.status,
        result=extraction.result,
        ocr_provider_used=extraction.ocr_provider_used,
        llm_provider_used=extraction.llm_provider_used,
        llm_model_used=extraction.llm_model_used,
        completed_at=extraction.completed_at,
    )


@router.get("/{extraction_id}/validation", response_model=ExtractionValidationResponse)
async def get_extraction_validation(
    extraction_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ExtractionValidationResponse:
    """Get the validation / review status for an extraction."""
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    errors = extraction.validation_errors or []
    return ExtractionValidationResponse(
        extraction_id=extraction.id,
        status=extraction.status,
        validation_errors=errors,
        validation_results=extraction.validation_results,
        review_verdict=extraction.review_verdict,
        completed_at=extraction.completed_at,
    )


@router.get("/{extraction_id}/steps", response_model=list[ExtractionStepResponse])
async def get_extraction_steps(
    extraction_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> list[ExtractionStep]:
    """Get pipeline step records for an extraction."""
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return extraction.steps


# ── Review endpoints ─────────────────────────────────────────────────


@router.post(
    "/{extraction_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_review(
    extraction_id: str,
    body: ReviewCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> ExtractionReview:
    """Submit a human review decision for an extraction.

    Only extractions in ``needs_review`` status accept reviews.
    If the decision is ``corrected``, ``corrected_fields`` must be
    provided and will be merged into the extraction result.
    An ``approved`` review transitions the extraction to ``completed``.
    A ``rejected`` review transitions the extraction to ``failed``.
    """
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")

    if extraction.status != "needs_review":
        raise HTTPException(
            status_code=409,
            detail=f"Only extractions in needs_review status can be reviewed (current: {extraction.status})",
        )

    if body.decision == "corrected" and not body.corrected_fields:
        raise HTTPException(
            status_code=422,
            detail="corrected_fields is required when decision is 'corrected'",
        )

    # Persist the review record
    review = ExtractionReview(
        extraction_id=extraction_id,
        decision=body.decision,
        corrected_fields=body.corrected_fields,
        notes=body.notes,
    )
    db.add(review)

    # Apply the review decision to the extraction
    now = _dt.datetime.now(_dt.UTC)

    if body.decision == "approved":
        extraction.status = "completed"
        extraction.review_verdict = "approved"
        extraction.validation_errors = None
        extraction.validation_results = None
        extraction.error = None
        extraction.error_category = None
        extraction.reviewed_at = now

    elif body.decision == "corrected":
        # Merge corrections into the existing result
        current_result = dict(extraction.result or {})
        current_result.update(body.corrected_fields)
        extraction.result = current_result
        if extraction.confidence:
            remaining_confidence = dict(extraction.confidence)
            for field_name in body.corrected_fields:
                remaining_confidence.pop(field_name, None)
            extraction.confidence = remaining_confidence or None
        extraction.status = "completed"
        extraction.review_verdict = "corrected"
        extraction.validation_errors = None
        extraction.validation_results = None
        extraction.error = None
        extraction.error_category = None
        extraction.reviewed_at = now

    elif body.decision == "rejected":
        extraction.status = "failed"
        extraction.review_verdict = "rejected"
        extraction.validation_errors = None
        extraction.validation_results = None
        extraction.error = body.notes or "Rejected by reviewer"
        extraction.error_category = "validation"
        extraction.reviewed_at = now

    # Safety: ensure completed_at is set if the pipeline didn't set it
    if not extraction.completed_at:
        extraction.completed_at = now

    await db.commit()
    await db.refresh(review)
    _metrics.reviews_total.labels(decision=body.decision.value).inc()
    await record_audit_event(
        db,
        extraction_id=extraction.id,
        event=AUDIT_EVENT_REVIEW_SUBMITTED,
        payload={"decision": body.decision.value},
    )
    await db.commit()
    return review


@router.get("/{extraction_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    extraction_id: str,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> list[ExtractionReview]:
    """List all review records for an extraction."""
    _apply_no_store_headers(response)
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return extraction.reviews
