"""Quality-gated preparation and finalization for targeted reprocessing runs."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.db_models import ParseJob, ReprocessRun
from app.models.enums import JobStatus
from app.models.schemas import ParseSettings
from app.services.parsing.contracts import BoundingBox, DocumentLayout
from app.services.parsing.inspection import (
    load_page_diagnostics,
    load_page_layout,
    render_source_page,
)
from app.services.parsing.markdown import MarkdownRenderer
from app.services.parsing.review import ReviewUnavailable
from app.services.parsing.runtime import ParserRuntime
from app.services.parsing.storage import ObjectStore


async def _job_with_runs(session: AsyncSession, job_id: str) -> ParseJob | None:
    statement = (
        select(ParseJob)
        .where(ParseJob.id == job_id)
        .options(
            selectinload(ParseJob.pages),
            selectinload(ParseJob.reprocess_runs),
            selectinload(ParseJob.review_cases),
        )
    )
    result = await session.execute(statement)
    # Lightweight worker harnesses may implement only row-count results. They
    # represent ordinary jobs, for which reprocessing is intentionally a no-op.
    scalar = getattr(result, "scalar_one_or_none", None)
    return scalar() if scalar else None


def active_reprocess(job: ParseJob) -> ReprocessRun | None:
    return next(
        (item for item in reversed(job.reprocess_runs) if item.status in {"queued", "running"}),
        None,
    )


def _expanded(box: BoundingBox, padding: float) -> BoundingBox:
    width = box.right - box.left
    height = box.bottom - box.top
    return BoundingBox(
        left=max(0, box.left - width * padding),
        top=max(0, box.top - height * padding),
        right=min(1, box.right + width * padding),
        bottom=min(1, box.bottom + height * padding),
    )


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


async def prepare_reprocess(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    runtime: ParserRuntime,
) -> None:
    async with sessions() as session:
        job = await _job_with_runs(session, job_id)
        if job is None or (run := active_reprocess(job)) is None:
            return
        run.status = "running"
        await session.commit()
        if run.target_kind == "page":
            return
        settings = ParseSettings.model_validate(job.settings)
        if not settings.ocr_model:
            raise RuntimeError("Region reprocessing requires a selected OCR repair model")
        layout = load_page_layout(job, run.page_number, store)
        diagnostics = load_page_diagnostics(job, run.page_number, store)
        region_index = next(
            (index for index, item in enumerate(layout.regions) if item.id == run.region_id),
            None,
        )
        if region_index is None:
            raise RuntimeError("Reprocessing region no longer exists")
        original = layout.regions[region_index]
        image_png = render_source_page(job, run.page_number, run.dpi, store)
        work_dir_factory = getattr(store, "work_dir", None)
        if work_dir_factory is None:
            raise RuntimeError("Region reprocessing requires filesystem-backed storage")
        work_dir = work_dir_factory(f"jobs/{job.id}/reprocessing/{run.id}")
        image_path = Path(work_dir) / f"page-{run.page_number:04d}.png"
        image_path.write_bytes(image_png)
        expanded = original.model_copy(update={"bbox": _expanded(original.bbox, run.crop_padding)})
        processed = await runtime.parser.process_zone(
            image_path,
            expanded,
            settings.layout_device,
            settings.ocr_model,
            settings.ocr_provider,
        )
        processed = processed.model_copy(
            update={
                "id": original.id,
                "bbox": original.bbox,
                "order": original.order,
                "parent_id": original.parent_id,
            }
        )
        candidate_page = layout.model_copy(deep=True)
        candidate_page.regions[region_index] = processed
        old_score = (
            diagnostics.quality_score.overall if diagnostics and diagnostics.quality_score else 0.0
        )
        old_status = (
            next(
                (
                    item.final_status
                    for item in diagnostics.region_decisions
                    if item.observation.region_id == run.region_id
                ),
                None,
            )
            if diagnostics
            else None
        )
        provider = (
            settings.review_provider if settings.cloud_mode != "off" else settings.ocr_provider
        )
        model = settings.review_model if settings.cloud_mode != "off" else settings.ocr_model
        score = 0.0
        verdict = "warn"
        reason = "No reviewer result"
        if model:
            reviewer = runtime.reviewer(provider, model)
            markdown = (
                MarkdownRenderer()
                .render(DocumentLayout(pages=[candidate_page]), settings.marginalia_policy)
                .clean
            )
            try:
                review = await reviewer.review(
                    image_png,
                    markdown,
                    [item.id or "unknown" for item in candidate_page.regions],
                    {
                        item.id or "unknown": [
                            candidate.content for candidate in item.recognition_candidates
                        ]
                        for item in candidate_page.regions
                    },
                    {
                        item.id or "unknown": {
                            "bbox": item.bbox.model_dump(mode="json"),
                            "type": item.type,
                            "order": item.order,
                        }
                        for item in candidate_page.regions
                    },
                )
                score = review.score.overall
                region_review = next(
                    (item for item in review.regions if item.region_id == run.region_id), None
                )
                verdict = region_review.verdict if region_review else "warn"
                reason = region_review.reason if region_review else "Reviewer omitted target region"
            except ReviewUnavailable as exc:
                reason = str(exc)
        thresholds = (job.quality_policy_snapshot or {}).get("thresholds", {})
        minimum = float(thresholds.get("min_overall", 0.75))
        accepted = (
            bool(processed.content.strip())
            and verdict == "pass"
            and score >= max(minimum, old_score)
        )
        if not accepted and old_status == "fail" and processed.content.strip() and score >= minimum:
            accepted = verdict != "fail"
        result_fingerprint = _fingerprint(candidate_page.model_dump(mode="json"))
        run.result_fingerprint = result_fingerprint
        run.decision = {
            **(run.decision or {}),
            "applied": accepted,
            "previous_score": old_score,
            "candidate_score": score,
            "verdict": verdict,
            "reason": reason,
            "provider": provider,
            "model": model,
        }
        if accepted:
            data = candidate_page.model_dump_json(indent=2).encode()
            store.write(f"jobs/{job.id}/checkpoints/p{run.page_number:04d}/layout.json", data)
            checkpoint = next(item for item in job.pages if item.page_number == run.page_number)
            checkpoint.layout_sha256 = hashlib.sha256(data).hexdigest()
            checkpoint.fingerprint = result_fingerprint
        await session.commit()


async def finalize_reprocess(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions() as session:
        job = await _job_with_runs(session, job_id)
        if job is None or (run := active_reprocess(job)) is None or run.status != "running":
            return
        if job.status not in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}:
            return
        decision = run.decision or {}
        if decision.get("applied", False):
            job.output_revision += 1
        previous_dpi = decision.get("previous_dpi")
        if previous_dpi in {150, 200, 300}:
            job.settings = {**job.settings, "dpi": previous_dpi}
        checkpoint = next((item for item in job.pages if item.page_number == run.page_number), None)
        if checkpoint is None or checkpoint.status != "completed":
            run.status = "failed"
            run.error_message = "Target page did not complete successfully"
            run.completed_at = dt.datetime.now(dt.UTC)
            previous_dpi = decision.get("previous_dpi")
            if previous_dpi in {150, 200, 300}:
                job.settings = {**job.settings, "dpi": previous_dpi}
            await session.commit()
            return
        run.result_fingerprint = run.result_fingerprint or checkpoint.fingerprint
        run.status = "completed"
        run.completed_at = dt.datetime.now(dt.UTC)
        await session.commit()


async def fail_reprocess(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    message: str,
) -> None:
    async with sessions() as session:
        job = await _job_with_runs(session, job_id)
        if job is None or (run := active_reprocess(job)) is None:
            return
        run.status = "failed"
        run.error_message = message
        run.completed_at = dt.datetime.now(dt.UTC)
        previous_dpi = (run.decision or {}).get("previous_dpi")
        if previous_dpi in {150, 200, 300}:
            job.settings = {**job.settings, "dpi": previous_dpi}
        await session.commit()
