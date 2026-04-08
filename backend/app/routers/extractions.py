"""Extraction job endpoints — run and retrieve extractions."""

import asyncio
import datetime
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, async_session
from app.models.db_models import Document, Extraction, ExtractionSchema, ExtractionStep, ExtractionReview
from app.models.schemas import (
    ExtractionCreate,
    ExtractionResponse,
    ExtractionResultResponse,
    ExtractionStepResponse,
    ExtractionValidationResponse,
    ReviewCreate,
    ReviewResponse,
)

router = APIRouter(prefix="/api/extractions", tags=["Extractions"])

logger = logging.getLogger(__name__)

# Maximum wall-clock time for a single extraction job (seconds).
_JOB_TIMEOUT = 300


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
    except asyncio.TimeoutError:
        logger.error("Extraction %s timed out after %ds", extraction_id, _JOB_TIMEOUT)
        async with async_session() as db:
            extraction = await db.get(Extraction, extraction_id)
            if extraction and extraction.status not in ("completed", "needs_review", "failed"):
                extraction.status = "failed"
                extraction.error = f"Job timed out after {_JOB_TIMEOUT}s. Please retry."
                await db.commit()
    except Exception:
        logger.exception("Unexpected error in extraction job %s", extraction_id)
        async with async_session() as db:
            extraction = await db.get(Extraction, extraction_id)
            if extraction and extraction.status not in ("completed", "needs_review", "failed"):
                extraction.status = "failed"
                extraction.error = "An unexpected error occurred. Please retry."
                await db.commit()


async def _run_extraction_pipeline(extraction_id: str) -> None:
    """Core pipeline logic with step-level persistence.

    Uses ``astream(stream_mode="updates")`` so each LangGraph node's
    output is captured as an ``ExtractionStep`` row with timing.  The
    extraction's status is updated after every node, making intermediate
    progress visible to frontend polls.
    """
    from app.services.extraction.graph import extraction_graph, PipelineState

    _ALL_STEPS = ("parse", "extract", "validate", "finalize")

    async with async_session() as db:
        extraction = await db.get(Extraction, extraction_id)
        if not extraction:
            return

        extraction.status = "processing"
        extraction.started_at = datetime.datetime.now(datetime.UTC)
        await db.commit()

        schema = await db.get(ExtractionSchema, extraction.schema_id)
        if not schema:
            extraction.status = "failed"
            extraction.error = "Schema not found"
            await db.commit()
            return

        doc = await db.get(Document, extraction.document_id)
        if not doc:
            extraction.status = "failed"
            extraction.error = "Document not found"
            await db.commit()
            return

        initial_state: PipelineState = {
            "file_path": doc.file_path,
            "schema_fields": schema.fields,
            "ocr_provider_id": extraction.ocr_provider,
            "llm_provider_id": extraction.llm_provider,
            "llm_model_id": extraction.llm_model,
            "extraction_id": extraction.id,
            "document_id": extraction.document_id,
            "schema_id": extraction.schema_id,
            "status": "pending",
            "error": "",
        }

        accumulated: dict = {}
        created_steps: dict[str, ExtractionStep] = {}
        step_start = datetime.datetime.now(datetime.UTC)
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
                initial_state, stream_mode="updates",
            ):
                node_name = next(iter(chunk))
                if node_name not in _ALL_STEPS:
                    continue  # skip __start__ / __end__

                node_output = chunk[node_name]
                now = datetime.datetime.now(datetime.UTC)
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
                step_idx = _ALL_STEPS.index(node_name)
                if step_status != "failed" and step_idx + 1 < len(_ALL_STEPS):
                    next_name = _ALL_STEPS[step_idx + 1]
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
        except Exception as exc:
            pipeline_error = f"Pipeline error: {exc}"
            # Mark any in-flight step as failed
            if current_step.status == "running":
                current_step.status = "failed"
                current_step.error = str(exc)
                current_step.completed_at = datetime.datetime.now(datetime.UTC)

        # Mark skipped steps (pipeline short-circuited on failure)
        for name in _ALL_STEPS:
            if name not in created_steps:
                db.add(ExtractionStep(
                    extraction_id=extraction_id,
                    name=name,
                    status="skipped",
                ))

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
                extraction.completed_at = datetime.datetime.fromisoformat(completed_at)

        # Classify the error for reviewer triage
        from app.services.extraction.error_classify import classify_error
        extraction.error_category = classify_error(extraction.error, extraction.status)

        await db.commit()


@router.post("/", response_model=ExtractionResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_extraction(
    body: ExtractionCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Extraction:
    """Start a new extraction job (runs in background)."""
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
    )
    db.add(extraction)
    await db.commit()
    await db.refresh(extraction)

    background_tasks.add_task(_run_extraction_job, extraction.id)
    return extraction


@router.post(
    "/{extraction_id}/retry",
    response_model=ExtractionResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_extraction(
    extraction_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Extraction:
    """Re-queue a failed extraction job.

    Only extractions in ``failed`` status can be retried.  The row is
    reset to ``queued`` and re-submitted to the background worker.
    """
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
    await db.execute(
        delete(ExtractionStep).where(ExtractionStep.extraction_id == extraction_id)
    )

    await db.commit()
    await db.refresh(extraction)

    background_tasks.add_task(_run_extraction_job, extraction.id)
    return extraction


@router.get("/", response_model=list[ExtractionResponse])
async def list_extractions(
    document_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[Extraction]:
    """List extractions, optionally filtered by document."""
    stmt = select(Extraction).order_by(Extraction.created_at.desc())
    if document_id:
        stmt = stmt.where(Extraction.document_id == document_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{extraction_id}", response_model=ExtractionResponse)
async def get_extraction(
    extraction_id: str,
    db: AsyncSession = Depends(get_db),
) -> Extraction:
    """Get extraction status and results."""
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return extraction


# ── SSE live progress stream ─────────────────────────────────────────


_SSE_POLL_INTERVAL = 1.0  # seconds between DB polls
_SSE_TERMINAL = frozenset({"completed", "needs_review", "failed"})


@router.get("/{extraction_id}/stream")
async def stream_extraction_progress(extraction_id: str) -> StreamingResponse:
    """Stream extraction progress as Server-Sent Events.

    Emits a JSON event each time the extraction status or step count
    changes.  Closes automatically when the extraction reaches a
    terminal state (completed / needs_review / failed).
    """

    async def _event_generator():
        last_status: str | None = None
        last_step_count = -1

        while True:
            async with async_session() as db:
                extraction = await db.get(Extraction, extraction_id)
                if not extraction:
                    yield _sse_event({"error": "Extraction not found"})
                    return

                steps = extraction.steps or []
                cur_status = extraction.status
                cur_step_count = len(steps)

                # Only emit when something changed
                if cur_status != last_status or cur_step_count != last_step_count:
                    payload = ExtractionResponse.model_validate(extraction)
                    yield _sse_event(payload.model_dump(mode="json"))
                    last_status = cur_status
                    last_step_count = cur_step_count

                if cur_status in _SSE_TERMINAL:
                    return

            await asyncio.sleep(_SSE_POLL_INTERVAL)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(data: dict) -> str:
    """Format a dict as a single SSE ``data:`` frame."""
    return f"data: {json.dumps(data, default=str)}\n\n"


@router.get("/{extraction_id}/result", response_model=ExtractionResultResponse)
async def get_extraction_result(
    extraction_id: str,
    db: AsyncSession = Depends(get_db),
) -> ExtractionResultResponse:
    """Get only the extraction result data."""
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
    db: AsyncSession = Depends(get_db),
) -> ExtractionValidationResponse:
    """Get the validation / review status for an extraction."""
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
    db: AsyncSession = Depends(get_db),
) -> list[ExtractionStep]:
    """Get pipeline step records for an extraction."""
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
    db: AsyncSession = Depends(get_db),
) -> ExtractionReview:
    """Submit a human review decision for an extraction.

    Only extractions in ``needs_review`` status accept reviews.
    If the decision is ``corrected``, ``corrected_fields`` must be
    provided and will be merged into the extraction result.
    An ``approved`` review transitions the extraction to ``completed``.
    A ``rejected`` review transitions the extraction to ``failed``.
    """
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
    now = datetime.datetime.now(datetime.UTC)

    if body.decision == "approved":
        extraction.status = "completed"
        extraction.review_verdict = "approved"
        extraction.completed_at = now
        extraction.reviewed_at = now

    elif body.decision == "corrected":
        # Merge corrections into the existing result
        current_result = dict(extraction.result or {})
        current_result.update(body.corrected_fields)
        extraction.result = current_result
        extraction.status = "completed"
        extraction.review_verdict = "corrected"
        extraction.validation_errors = None
        extraction.completed_at = now
        extraction.reviewed_at = now

    elif body.decision == "rejected":
        extraction.status = "failed"
        extraction.review_verdict = "rejected"
        extraction.error = body.notes or "Rejected by reviewer"
        extraction.completed_at = now
        extraction.reviewed_at = now

    await db.flush()
    await db.refresh(review)
    return review


@router.get("/{extraction_id}/reviews", response_model=list[ReviewResponse])
async def list_reviews(
    extraction_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ExtractionReview]:
    """List all review records for an extraction."""
    extraction = await db.get(Extraction, extraction_id)
    if not extraction:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return extraction.reviews
