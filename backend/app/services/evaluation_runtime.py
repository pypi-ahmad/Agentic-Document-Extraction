"""Persist evaluation results when linked parse jobs become terminal."""

from __future__ import annotations

import asyncio
import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models.db_models import EvaluationCase, EvaluationRun, ParseJob
from app.models.enums import ArtifactType, JobStatus
from app.services.evaluation import GroundTruthDocument, evaluate_document
from app.services.parsing.contracts import DocumentLayout, PageLayout
from app.services.parsing.segmentation import DetectedSubDocument, IdentifierEvidence
from app.services.parsing.storage import ObjectStore


async def finalize_evaluations_for_job(
    sessions: async_sessionmaker[AsyncSession], store: ObjectStore, job_id: str
) -> None:
    async with sessions() as session:
        cases = list(
            await session.scalars(
                select(EvaluationCase)
                .where(EvaluationCase.parse_job_id == job_id, EvaluationCase.status == "pending")
                .options(selectinload(EvaluationCase.run))
            )
        )
        if not cases:
            return
        job = (
            await session.execute(
                select(ParseJob)
                .where(ParseJob.id == job_id)
                .options(
                    selectinload(ParseJob.pages),
                    selectinload(ParseJob.artifacts),
                    selectinload(ParseJob.subdocuments),
                )
            )
        ).scalar_one_or_none()
        if job is None:
            return
        if job.status in {
            JobStatus.QUEUED,
            JobStatus.INSPECTING,
            JobStatus.PROCESSING,
            JobStatus.ASSEMBLING,
            JobStatus.CANCELLING,
            JobStatus.PAUSED,
        }:
            return
        for case in cases:
            if job.status not in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}:
                case.status = "failed"
                case.error_message = job.error_message or f"Parse job ended in {job.status}"
                case.completed_at = dt.datetime.now(dt.UTC)
                continue
            try:
                gold = GroundTruthDocument.model_validate_json(
                    await asyncio.to_thread(store.read, case.gold_path)
                )
                if gold.source_sha256 and gold.source_sha256 != job.source_sha256:
                    raise ValueError("ground-truth source hash does not match the parsed document")
                markdown_artifact = next(
                    item for item in job.artifacts if item.type == ArtifactType.CLEAN_MARKDOWN
                )
                markdown = (
                    await asyncio.to_thread(store.read, markdown_artifact.relative_path)
                ).decode()
                pages = [
                    PageLayout.model_validate_json(
                        await asyncio.to_thread(store.read, page.layout_path)
                    )
                    for page in job.pages
                    if page.layout_path
                ]
                predicted_subdocuments = [
                    DetectedSubDocument(
                        ordinal=item.ordinal,
                        start_page=item.start_page,
                        end_page=item.end_page,
                        profile=item.profile,
                        confidence=item.confidence,
                        identifiers=[
                            IdentifierEvidence.model_validate(value)
                            for value in (item.identifiers or [])
                        ],
                        boundary_confidence=item.boundary_confidence,
                        boundary_reasons=item.boundary_reasons or [],
                        complete=item.complete,
                        missing_pages=item.missing_pages or [],
                        warnings=item.warnings or [],
                    )
                    for item in job.subdocuments
                ]
                report = evaluate_document(
                    markdown,
                    DocumentLayout(pages=pages),
                    gold,
                    predicted_subdocuments,
                )
                data = report.model_dump_json(indent=2).encode()
                report_path = f"evaluations/{case.run_id}/cases/{case.id}.json"
                await asyncio.to_thread(store.write, report_path, data)
                case.status = "completed"
                case.metrics = report.metrics
                case.report_path = report_path
                case.completed_at = dt.datetime.now(dt.UTC)
            except (KeyError, OSError, StopIteration, ValueError) as exc:
                case.status = "failed"
                case.error_message = str(exc) or type(exc).__name__
                case.completed_at = dt.datetime.now(dt.UTC)
        await session.commit()
        run_ids = {case.run_id for case in cases}
    for run_id in run_ids:
        await _aggregate_run(sessions, store, run_id)


async def _aggregate_run(
    sessions: async_sessionmaker[AsyncSession], store: ObjectStore, run_id: str
) -> None:
    async with sessions() as session:
        run = (
            await session.execute(
                select(EvaluationRun)
                .where(EvaluationRun.id == run_id)
                .options(selectinload(EvaluationRun.cases))
            )
        ).scalar_one_or_none()
        if run is None:
            return
        run.completed_cases = sum(case.status == "completed" for case in run.cases)
        run.failed_cases = sum(case.status == "failed" for case in run.cases)
        if run.completed_cases + run.failed_cases < run.total_cases:
            run.status = "running"
            await session.commit()
            return
        metric_sets = [case.metrics for case in run.cases if case.metrics]
        keys = sorted({key for metrics in metric_sets for key in metrics})
        run.metrics = {
            key: sum(float(metrics[key]) for metrics in metric_sets if key in metrics)
            / sum(key in metrics for metrics in metric_sets)
            for key in keys
        }
        run.status = "completed_with_failures" if run.failed_cases else "completed"
        run.completed_at = dt.datetime.now(dt.UTC)
        payload = {
            "schema_version": "paperplane-eval/v1",
            "run_id": run.id,
            "status": run.status,
            "metrics": run.metrics,
            "total_cases": run.total_cases,
            "completed_cases": run.completed_cases,
            "failed_cases": run.failed_cases,
            "cases": [
                {
                    "id": case.id,
                    "external_id": case.external_id,
                    "parse_job_id": case.parse_job_id,
                    "status": case.status,
                    "metrics": case.metrics,
                    "error_message": case.error_message,
                }
                for case in run.cases
            ],
        }
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode()
        path = f"evaluations/{run.id}/report.json"
        await asyncio.to_thread(store.write, path, data)
        run.report_path = path
        await session.commit()
