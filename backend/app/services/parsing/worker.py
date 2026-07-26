"""Durable job runner for the document-wide layout parsing graph."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import settings as app_settings
from app.logging_setup import get_logger
from app.models.db_models import Artifact, ParseJob, SubDocument
from app.models.enums import ArtifactType, JobStatus, PageStatus
from app.models.schemas import ParseSettings
from app.services.evaluation_runtime import finalize_evaluations_for_job
from app.services.parsing.agentic_contracts import PageDiagnostics, PagePlan
from app.services.parsing.artifacts import build_bundle, build_grounding_pdf, build_searchable_pdf
from app.services.parsing.contracts import ContextChunk, DocumentLayout, PageLayout
from app.services.parsing.diagnostics import build_page_diagnostics
from app.services.parsing.domain_extraction import DomainExtraction, extract_domain
from app.services.parsing.glmocr_adapter import GLMOCRAdapter, GLMOCRUnavailable
from app.services.parsing.markdown import render_llm_markdown
from app.services.parsing.paddleocr_vl import PaddleOCRVLUnavailable
from app.services.parsing.parser import LayoutParser
from app.services.parsing.public_diagnostics import to_public_diagnostics
from app.services.parsing.reprocessing import (
    active_reprocess,
    fail_reprocess,
    finalize_reprocess,
    prepare_reprocess,
)
from app.services.parsing.review_cases import sync_grounded_review_case, sync_page_review_cases
from app.services.parsing.runtime import ParserRuntime
from app.services.parsing.schema_extraction import (
    ExtractionScope,
    SchemaExtractionBundle,
    SchemaExtractionDocument,
    SchemaExtractionInstance,
    extract_schema_instance,
)
from app.services.parsing.schema_models import SchemaModelClient
from app.services.parsing.segmentation import DetectedSubDocument, segment_document
from app.services.parsing.storage import ObjectStore
from app.services.parsing.structured_blocks import (
    StructuredDocument,
    apply_source_geometry,
    build_structured_document,
)
from app.services.parsing.subdocument_artifacts import build_subdocument_payloads

logger = get_logger("app.parsing.worker")


async def _load_job(session: AsyncSession, job_id: str) -> ParseJob | None:
    statement = (
        select(ParseJob)
        .where(ParseJob.id == job_id)
        .options(
            selectinload(ParseJob.pages),
            selectinload(ParseJob.artifacts),
            selectinload(ParseJob.reprocess_runs),
        )
    )
    return (await session.execute(statement)).scalar_one_or_none()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact(
    job_id: str,
    run_id: str,
    kind: str,
    filename: str,
    data: bytes,
    mime: str,
    region_id: str | None = None,
) -> Artifact:
    return Artifact(
        id=uuid.uuid4().hex,
        job_id=job_id,
        type=kind,
        region_id=region_id,
        relative_path=f"jobs/{job_id}/artifacts/{run_id}/{filename}",
        mime_type=mime,
        size=len(data),
        sha256=_sha256(data),
    )


def _subdocument_artifact(
    job_id: str,
    subdocument_id: str,
    run_id: str,
    kind: str,
    filename: str,
    data: bytes,
    mime: str,
    region_id: str | None = None,
) -> Artifact:
    return Artifact(
        id=uuid.uuid4().hex,
        job_id=job_id,
        subdocument_id=subdocument_id,
        type=kind,
        region_id=region_id,
        relative_path=(
            f"jobs/{job_id}/subdocuments/{subdocument_id}/artifacts/{run_id}/{filename}"
        ),
        mime_type=mime,
        size=len(data),
        sha256=_sha256(data),
    )


def _slice_structured_document(
    document: StructuredDocument, start_page: int, end_page: int
) -> StructuredDocument:
    return document.model_copy(
        update={
            "page_count": end_page - start_page + 1,
            "blocks": [block for block in document.blocks if start_page <= block.page <= end_page],
        }
    )


def _schema_document(
    snapshot: dict[str, Any],
    *,
    source_filename: str,
    source_sha256: str,
    instances: list[SchemaExtractionInstance],
) -> SchemaExtractionDocument:
    warnings = list(dict.fromkeys(item for instance in instances for item in instance.warnings))
    return SchemaExtractionDocument(
        schema=snapshot,
        source={"filename": source_filename, "sha256": source_sha256},
        complete=bool(instances) and all(instance.complete for instance in instances),
        instances=instances,
        warnings=warnings,
    )


def _schema_table_payloads(
    bundle: SchemaExtractionBundle, *, instance_key: str
) -> list[tuple[str, str, bytes, str, str | None]]:
    payloads: list[tuple[str, str, bytes, str, str | None]] = []
    for pointer, data in bundle.table_jsonl.items():
        slug = "-".join(part for part in pointer.strip("/").split("/") if part) or "table"
        slug = "".join(
            character if character.isalnum() or character in "-_" else "-" for character in slug
        )
        digest = hashlib.sha256(f"{instance_key}:{pointer}".encode()).hexdigest()[:32]
        payloads.append(
            (
                ArtifactType.SCHEMA_TABLE,
                f"tables/{slug[:80]}-{digest[:8]}.grounded.jsonl",
                data,
                "application/x-ndjson",
                digest,
            )
        )
    return payloads


async def run_parse_job(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    runtime: ParserRuntime | None = None,
    *_: Any,
    **__: Any,
) -> None:
    async with sessions() as session:
        claimed = await session.execute(
            update(ParseJob)
            .where(
                ParseJob.id == job_id,
                ParseJob.status == JobStatus.QUEUED,
                ParseJob.cancel_requested.is_(False),
            )
            .values(status=JobStatus.PROCESSING, started_at=dt.datetime.now(dt.UTC))
        )
        await session.commit()
        if claimed.rowcount != 1:
            return
    try:
        if runtime is None:
            transient = ParserRuntime(
                checkpoint_path=app_settings.langgraph_checkpoint_path,
                ollama_base_url=app_settings.ollama_base_url,
                paddleocr_vl_image=app_settings.paddleocr_vl_image,
                paddleocr_vl_cache_dir=app_settings.paddleocr_vl_cache_dir,
                timeout_seconds=max(
                    app_settings.glm_ocr_timeout_seconds,
                    app_settings.ollama_review_timeout_seconds,
                    app_settings.paddleocr_vl_timeout_seconds,
                ),
            )
            async with transient:
                await prepare_reprocess(job_id, sessions, store, transient)
                await _execute(job_id, sessions, store, transient)
                await finalize_reprocess(job_id, sessions)
        else:
            await prepare_reprocess(job_id, sessions, store, runtime)
            await _execute(job_id, sessions, store, runtime)
            await finalize_reprocess(job_id, sessions)
    except asyncio.CancelledError:
        await fail_reprocess(job_id, sessions, "Reprocessing was interrupted by server shutdown")
        await _terminalize(
            sessions,
            job_id,
            JobStatus.PAUSED,
            "server_shutdown",
            "Server shut down while this job was active; resume to continue.",
        )
        raise
    except PaddleOCRVLUnavailable as exc:
        await fail_reprocess(job_id, sessions, str(exc))
        logger.warning(
            "parse_job.paddleocr_vl_unavailable",
            job_id=job_id,
        )
        await _terminalize(
            sessions,
            job_id,
            JobStatus.FAILED,
            "paddleocr_vl_unavailable",
            str(exc),
        )
    except Exception as exc:
        await fail_reprocess(job_id, sessions, f"Reprocessing failed: {type(exc).__name__}")
        logger.exception(
            "parse_job.failed",
            job_id=job_id,
            exception_type=type(exc).__name__,
            exc_info=True,
        )
        await _terminalize(
            sessions, job_id, JobStatus.FAILED, "job_execution_failed", "Parse job failed"
        )
    finally:
        await _finalize_linked_evaluations(sessions, store, job_id)


def _page_batches(page_numbers: list[int], size: int) -> list[list[int]]:
    """Return consecutive batches so retries never reprocess successful pages between gaps."""
    batches: list[list[int]] = []
    current: list[int] = []
    for page_number in sorted(page_numbers):
        if current and (page_number != current[-1] + 1 or len(current) >= size):
            batches.append(current)
            current = []
        current.append(page_number)
    if current:
        batches.append(current)
    return batches


async def _run_batches(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    runtime: ParserRuntime,
    source_path: Path,
    work_dir: Path,
    parse_settings: ParseSettings,
    preflight_warnings: list[str],
) -> dict[str, Any] | None:
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return None
        pending = [
            page.page_number
            for page in job.pages
            if page.status != PageStatus.COMPLETED
            or not page.layout_path
            or not _stored_layout_is_valid(store, page.layout_path)
        ]

    aggregate: dict[str, Any] = {
        "warnings": list(preflight_warnings),
        "reviews": {},
        "visual_verifications": {},
        "figure_crops": {},
        "repair_count": 0,
    }
    runtime.paddleocr_vl.set_progress_callback(
        job_id,
        lambda page, event: _publish_page_progress(sessions, job_id, page, event),
    )
    for batch_index, page_numbers in enumerate(
        _page_batches(pending, app_settings.parse_batch_pages), start=1
    ):
        batch_result: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, app_settings.parse_batch_max_attempts + 1):
            batch_work_dir = (
                work_dir
                / "batches"
                / (f"p{page_numbers[0]:04d}-p{page_numbers[-1]:04d}-a{attempt}")
            )
            await asyncio.to_thread(batch_work_dir.mkdir, parents=True, exist_ok=True)
            state: dict[str, Any] = {
                "job_id": job_id,
                "source_path": str(source_path),
                "work_dir": str(batch_work_dir),
                "settings": parse_settings.model_dump(mode="json"),
                "page_numbers": page_numbers,
                "repair_count": 0,
                "max_repairs": min(
                    app_settings.max_page_repairs,
                    int(
                        (job.quality_policy_snapshot or {})
                        .get("thresholds", {})
                        .get("max_repairs", app_settings.max_page_repairs)
                    ),
                ),
                "warnings": [],
            }
            config = {
                "configurable": {
                    "thread_id": f"{job_id}:batch:{batch_index}:attempt:{attempt}:{uuid.uuid4().hex[:8]}"
                }
            }
            try:
                async for graph_update in runtime.graph.astream(
                    state, config, stream_mode="updates"
                ):
                    for node, values in graph_update.items():
                        state.update(values)
                        if await _publish_stage(sessions, job_id, node):
                            await runtime.paddleocr_vl.cancel(job_id)
                            return None
                batch_result = state
                await _persist_batch_result(
                    job_id, sessions, store, parse_settings, batch_result, attempt
                )
                break
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "parse_batch.failed",
                    job_id=job_id,
                    pages=page_numbers,
                    attempt=attempt,
                    exception_type=type(exc).__name__,
                )
        if batch_result is None:
            await _mark_batch_failed(job_id, sessions, page_numbers, last_error)
            aggregate["warnings"].append(f"pages:{page_numbers[0]}-{page_numbers[-1]}:batch_failed")
            continue
        aggregate["warnings"].extend(batch_result.get("warnings", []))
        aggregate["reviews"].update(batch_result.get("reviews", {}))
        aggregate["visual_verifications"].update(batch_result.get("visual_verifications", {}))
        aggregate["figure_crops"].update(batch_result.get("figure_crops", {}))
        aggregate["repair_count"] = max(
            aggregate["repair_count"], batch_result.get("repair_count", 0)
        )

    pages, missing_pages = await _load_checkpoint_layouts(job_id, sessions, store)
    if not pages:
        raise RuntimeError("No document pages completed successfully")
    parser = LayoutParser()
    layout = parser.build_document_layout(
        {page_number: page.regions for page_number, page in pages.items()}
    )
    stitched = parser.stitch_layout(layout, parse_settings.marginalia_policy)
    aggregate.update(
        {
            "layout": layout.model_dump(mode="json"),
            "markdown": _mark_missing_pages(stitched.clean_markdown, missing_pages),
            "grounded_markdown": _mark_missing_pages(stitched.grounded_markdown, missing_pages),
            "context": {
                "schema_version": "2",
                "complete": not missing_pages,
                "missing_pages": missing_pages,
                "chunks": [chunk.model_dump(mode="json") for chunk in stitched.context_chunks],
            },
        }
    )
    return aggregate


def _stored_layout_is_valid(store: ObjectStore, relative_path: str) -> bool:
    try:
        PageLayout.model_validate_json(store.read(relative_path))
        return True
    except (KeyError, OSError, ValueError):
        return False


async def _persist_batch_result(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    parse_settings: ParseSettings,
    result: dict[str, Any],
    attempt: int,
) -> None:
    layout = DocumentLayout.model_validate(result["layout"])
    reviews = result.get("reviews", {})
    visual = result.get("visual_verifications", {})
    plans = result.get("page_plans", {})
    records: dict[int, tuple[str, bytes, str, bytes, PageDiagnostics]] = {}
    for page in layout.pages:
        page_warnings = [
            item for item in result.get("warnings", []) if item.startswith(f"p{page.page_number}:")
        ]
        diagnostic = build_page_diagnostics(
            page,
            reviews.get(page.page_number) or reviews.get(str(page.page_number)),
            repair_count=result.get("repair_count", 0),
            warnings=page_warnings,
            visual_verifications=visual.get(page.page_number) or visual.get(str(page.page_number)),
            planned=PagePlan.model_validate(
                plans.get(page.page_number) or plans.get(str(page.page_number))
            )
            if (plans.get(page.page_number) or plans.get(str(page.page_number)))
            else None,
        )
        prefix = f"jobs/{job_id}/checkpoints/p{page.page_number:04d}"
        layout_path = f"{prefix}/layout.json"
        diagnostics_path = f"{prefix}/diagnostics.json"
        layout_data = page.model_dump_json(indent=2).encode()
        diagnostics_data = diagnostic.model_dump_json(indent=2).encode()
        await asyncio.to_thread(store.write, layout_path, layout_data)
        await asyncio.to_thread(store.write, diagnostics_path, diagnostics_data)
        records[page.page_number] = (
            layout_path,
            layout_data,
            diagnostics_path,
            diagnostics_data,
            diagnostic,
        )
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        reprocess = active_reprocess(job)
        for checkpoint in job.pages:
            record = records.get(checkpoint.page_number)
            if record is None:
                continue
            layout_path, layout_data, diagnostics_path, _, diagnostic = record
            if (
                reprocess is not None
                and reprocess.target_kind == "page"
                and reprocess.page_number == checkpoint.page_number
            ):
                previous_score = checkpoint.quality_score
                candidate_score = (
                    diagnostic.quality_score.overall if diagnostic.quality_score else 0.0
                )
                status_rank = {"fail": 0, "warn": 1, "pass": 2}
                accepted = (
                    previous_score is None or candidate_score >= previous_score
                ) and status_rank.get(str(diagnostic.quality_status), 0) >= status_rank.get(
                    str(checkpoint.quality_status), 0
                )
                reprocess.result_fingerprint = diagnostic.fingerprint
                reprocess.decision = {
                    **(reprocess.decision or {}),
                    "applied": accepted,
                    "previous_score": previous_score,
                    "candidate_score": candidate_score,
                    "previous_status": checkpoint.quality_status,
                    "candidate_status": diagnostic.quality_status,
                    "reason": (
                        "Candidate met or improved the stored quality result"
                        if accepted
                        else "Candidate did not improve the stored quality result"
                    ),
                }
                if not accepted:
                    before_layout_path = (reprocess.decision or {}).get("before_layout_path")
                    before_diagnostics_path = (reprocess.decision or {}).get(
                        "before_diagnostics_path"
                    )
                    if isinstance(before_layout_path, str):
                        previous_layout = await asyncio.to_thread(
                            store.read, before_layout_path
                        )
                        await asyncio.to_thread(store.write, layout_path, previous_layout)
                    if isinstance(before_diagnostics_path, str):
                        previous_diagnostics = await asyncio.to_thread(
                            store.read, before_diagnostics_path
                        )
                        await asyncio.to_thread(
                            store.write, diagnostics_path, previous_diagnostics
                        )
                    checkpoint.status = PageStatus.COMPLETED
                    checkpoint.stage = "completed"
                    checkpoint.fingerprint = reprocess.previous_fingerprint
                    continue
            checkpoint.status = PageStatus.COMPLETED
            checkpoint.stage = "completed"
            checkpoint.routing = parse_settings.input_mode
            checkpoint.layout_path = layout_path
            checkpoint.layout_sha256 = _sha256(layout_data)
            checkpoint.diagnostics_path = diagnostics_path
            checkpoint.fingerprint = diagnostic.fingerprint
            checkpoint.quality_status = diagnostic.quality_status
            checkpoint.quality_score = (
                diagnostic.quality_score.overall if diagnostic.quality_score else None
            )
            checkpoint.repair_count = diagnostic.repair_count
            checkpoint.attempts = max(checkpoint.attempts, attempt)
            checkpoint.error_code = None
            checkpoint.error_message = None
            await sync_page_review_cases(session, job_id, diagnostic, job.quality_policy_snapshot)
        job.completed_pages = sum(page.status == PageStatus.COMPLETED for page in job.pages)
        job.failed_pages = sum(page.status == PageStatus.FAILED for page in job.pages)
        await session.commit()


async def _mark_batch_failed(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    page_numbers: list[int],
    error: Exception | None,
) -> None:
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        for page in job.pages:
            if page.page_number in page_numbers:
                page.status = PageStatus.FAILED
                page.stage = "processing"
                page.attempts += app_settings.parse_batch_max_attempts
                page.error_code = "batch_failed"
                page.error_message = (
                    f"Batch failed after retries ({type(error).__name__})"
                    if error
                    else "Batch failed after retries"
                )
        job.failed_pages = sum(page.status == PageStatus.FAILED for page in job.pages)
        await session.commit()


async def _load_checkpoint_layouts(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
) -> tuple[dict[int, PageLayout], list[int]]:
    pages: dict[int, PageLayout] = {}
    missing: list[int] = []
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return {}, []
        for checkpoint in job.pages:
            if checkpoint.status != PageStatus.COMPLETED or not checkpoint.layout_path:
                missing.append(checkpoint.page_number)
                continue
            try:
                pages[checkpoint.page_number] = PageLayout.model_validate_json(
                    await asyncio.to_thread(store.read, checkpoint.layout_path)
                )
            except (KeyError, OSError, ValueError):
                missing.append(checkpoint.page_number)
    return pages, sorted(missing)


def _mark_missing_pages(markdown: str, missing_pages: list[int]) -> str:
    if not missing_pages:
        return markdown
    marker = ", ".join(str(page) for page in missing_pages)
    return f"> [!WARNING]\n> Incomplete document. Missing pages: {marker}.\n\n{markdown}"


async def _execute(
    job_id: str,
    sessions: async_sessionmaker[AsyncSession],
    store: ObjectStore,
    runtime: ParserRuntime,
) -> None:
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        parse_settings = ParseSettings.model_validate(job.settings)
        source = await asyncio.to_thread(store.read, job.source_path)
        work_dir_factory = getattr(store, "work_dir", None)
        if work_dir_factory is None:
            raise RuntimeError("The graph runner requires a filesystem-backed object store")
        work_dir = await asyncio.to_thread(work_dir_factory, f"jobs/{job_id}/runtime")
        source_path = work_dir / f"source{Path(job.original_filename).suffix.lower()}"
        await asyncio.to_thread(source_path.write_bytes, source)

    local_models = {
        model
        for provider, model in (
            (parse_settings.ocr_provider, parse_settings.ocr_model),
            (
                parse_settings.review_provider,
                parse_settings.review_model if parse_settings.cloud_mode != "off" else None,
            ),
            (
                parse_settings.extraction_provider,
                parse_settings.extraction_model if job.extraction_schema_snapshot else None,
            ),
        )
        if provider == "ollama" and model
    }
    preflight_warnings = await _unload_local_models(runtime, local_models, report_resident=True)
    result: dict[str, Any] | None = None
    try:
        result = await _run_batches(
            job_id,
            sessions,
            store,
            runtime,
            source_path,
            work_dir,
            parse_settings,
            preflight_warnings,
        )
        if result is None:
            return
    finally:
        runtime.paddleocr_vl.set_progress_callback(job_id, None)
        unload_warnings = await _unload_local_models(runtime, local_models)
        if result is not None:
            result.setdefault("warnings", []).extend(unload_warnings)

    if result is None:
        return

    if await _finish_cancel_if_requested(sessions, job_id):
        return

    warnings = list(dict.fromkeys(result.get("warnings", [])))
    layout = apply_source_geometry(
        DocumentLayout.model_validate(result["layout"]), source, job.original_filename
    ).with_stable_ids()
    structured_document = build_structured_document(
        layout,
        source_filename=job.original_filename,
        source_sha256=job.source_sha256,
    )
    block_by_id = {block.id: block for block in structured_document.blocks}
    for chunk in result["context"].get("chunks", []):
        block = block_by_id.get(chunk.get("id"))
        if block is not None:
            chunk["source_bbox"] = block.source_bbox.model_dump(mode="json")
            chunk["page_width"] = block.page_width
            chunk["page_height"] = block.page_height
            if block.cells:
                chunk.setdefault("metadata", {})["table_cells"] = [
                    cell.model_dump(mode="json") for cell in block.cells
                ]
    reviews = result.get("reviews", {})
    visual_verifications = result.get("visual_verifications", {})
    diagnostics: list[PageDiagnostics] = []
    checkpoint_files: dict[int, dict[str, tuple[str, bytes]]] = {}
    public_pages: list[dict[str, Any]] = []
    for page in layout.pages:
        page_warnings = [item for item in warnings if item.startswith(f"p{page.page_number}:")]
        diagnostic = build_page_diagnostics(
            page,
            reviews.get(page.page_number) or reviews.get(str(page.page_number)),
            repair_count=result.get("repair_count", 0),
            warnings=page_warnings,
            visual_verifications=visual_verifications.get(page.page_number)
            or visual_verifications.get(str(page.page_number)),
        )
        diagnostics.append(diagnostic)
        public_pages.append(to_public_diagnostics(diagnostic).model_dump(mode="json"))
        prefix = f"jobs/{job_id}/checkpoints/p{page.page_number:04d}"
        layout_data = json.dumps(
            page.model_dump(mode="json"), ensure_ascii=False, indent=2
        ).encode()
        diagnostics_data = diagnostic.model_dump_json(indent=2).encode()
        checkpoint_files[page.page_number] = {
            "layout": (f"{prefix}/layout.json", layout_data),
            "diagnostics": (f"{prefix}/diagnostics.json", diagnostics_data),
        }

    settings_data = json.dumps(
        parse_settings.model_dump(mode="json"), ensure_ascii=False, indent=2
    ).encode()
    aggregate_diagnostics = json.dumps(
        {"schema_version": "1", "pages": public_pages}, ensure_ascii=False, indent=2
    ).encode()
    domain_extraction: DomainExtraction | None = None
    if parse_settings.structured_extraction:
        context_chunks = [
            ContextChunk.model_validate(chunk) for chunk in result["context"].get("chunks", [])
        ]
        domain_extraction = extract_domain(
            context_chunks,
            parse_settings.document_profile,
            expected_pages=[page.page_number for page in job.pages],
        )
    schema_snapshot = job.extraction_schema_snapshot
    schema_instances: list[SchemaExtractionInstance] = []
    schema_table_payloads: list[tuple[str, str, bytes, str, str | None]] = []
    schema_model_client = (
        SchemaModelClient(runtime.client, runtime.provider_registry) if schema_snapshot else None
    )
    segments: list[DetectedSubDocument] = []
    subdocument_records: list[SubDocument] = []
    if parse_settings.segment_documents:
        context_chunks = [
            ContextChunk.model_validate(chunk) for chunk in result["context"].get("chunks", [])
        ]
        segments = segment_document(
            context_chunks,
            expected_pages=[page.page_number for page in job.pages],
        )
        logger.info(
            "document.segmentation_complete",
            job_id=job_id,
            subdocument_count=len(segments),
            boundary_count=max(0, len(segments) - 1),
            incomplete_count=sum(not segment.complete for segment in segments),
        )
        for segment in segments:
            subdocument = SubDocument(
                id=uuid.uuid4().hex,
                job_id=job_id,
                ordinal=segment.ordinal,
                start_page=segment.start_page,
                end_page=segment.end_page,
                profile=segment.profile,
                confidence=segment.confidence,
                identifiers=[item.model_dump(mode="json") for item in segment.identifiers],
                boundary_confidence=segment.boundary_confidence,
                boundary_reasons=segment.boundary_reasons,
                complete=segment.complete,
                missing_pages=segment.missing_pages,
                warnings=list(segment.warnings),
            )
            try:
                segment_payloads = await asyncio.to_thread(
                    build_subdocument_payloads,
                    source=source,
                    source_filename=job.original_filename,
                    source_sha256=job.source_sha256,
                    layout=layout,
                    segment=segment,
                    settings=parse_settings,
                    figure_crops=result.get("figure_crops", {}),
                )
                if schema_snapshot and schema_model_client:
                    schema_bundle = await extract_schema_instance(
                        _slice_structured_document(
                            structured_document, segment.start_page, segment.end_page
                        ),
                        schema_snapshot["json_schema"],
                        scope=ExtractionScope(
                            subdocument_id=subdocument.id,
                            start_page=segment.start_page,
                            end_page=segment.end_page,
                        ),
                        processing_mode=parse_settings.processing_mode,
                        model_client=schema_model_client,
                        model_provider=parse_settings.extraction_provider,
                        model_name=parse_settings.extraction_model,
                    )
                    schema_instances.append(schema_bundle.instance)
                    segment_schema_document = _schema_document(
                        schema_snapshot,
                        source_filename=job.original_filename,
                        source_sha256=job.source_sha256,
                        instances=[schema_bundle.instance],
                    )
                    segment_payloads.append(
                        (
                            ArtifactType.SCHEMA_EXTRACTION,
                            "document.schema-extraction.json",
                            segment_schema_document.model_dump_json(
                                indent=2, by_alias=True
                            ).encode(),
                            "application/json",
                            None,
                        )
                    )
                    table_payloads = _schema_table_payloads(
                        schema_bundle, instance_key=subdocument.id
                    )
                    segment_payloads.extend(table_payloads)
                    schema_table_payloads.extend(
                        _schema_table_payloads(
                            schema_bundle, instance_key=f"parent-{subdocument.id}"
                        )
                    )
                    if not schema_bundle.instance.complete:
                        warning = f"subdocument:{segment.ordinal}:schema_extraction_incomplete"
                        subdocument.warnings = [*subdocument.warnings, warning]
                        warnings.append(warning)
                segment_run_id = uuid.uuid4().hex
                for payload in segment_payloads:
                    record = _subdocument_artifact(job_id, subdocument.id, segment_run_id, *payload)
                    await asyncio.to_thread(store.write, record.relative_path, payload[2])
                    subdocument.artifacts.append(record)
            except Exception as exc:
                warning = f"subdocument:{segment.ordinal}:artifact_failed:{type(exc).__name__}"
                subdocument.warnings = [*subdocument.warnings, warning]
                warnings.append(warning)
            subdocument_records.append(subdocument)
    if schema_snapshot and schema_model_client and not schema_instances:
        schema_bundle = await extract_schema_instance(
            structured_document,
            schema_snapshot["json_schema"],
            scope=ExtractionScope(
                start_page=parse_settings.start_page,
                end_page=parse_settings.end_page or job.page_count,
            ),
            processing_mode=parse_settings.processing_mode,
            model_client=schema_model_client,
            model_provider=parse_settings.extraction_provider,
            model_name=parse_settings.extraction_model,
        )
        schema_instances.append(schema_bundle.instance)
        schema_table_payloads.extend(_schema_table_payloads(schema_bundle, instance_key=job_id))
        if not schema_bundle.instance.complete:
            warnings.append("schema_extraction_incomplete")
    if schema_snapshot and parse_settings.extraction_provider == "ollama":
        warnings.extend(
            await _unload_local_models(
                runtime,
                {parse_settings.extraction_model} if parse_settings.extraction_model else set(),
            )
        )
    payloads: list[tuple[str, str, bytes, str, str | None]] = [
        (
            ArtifactType.CLEAN_MARKDOWN,
            "document.md",
            result["markdown"].encode(),
            "text/markdown",
            None,
        ),
        (
            ArtifactType.LLM_MARKDOWN,
            "document.llm.md",
            render_llm_markdown(
                layout,
                source_filename=job.original_filename,
                source_sha256=job.source_sha256,
                marginalia_policy=parse_settings.marginalia_policy,
            ).encode(),
            "text/markdown",
            None,
        ),
        (
            ArtifactType.GROUNDED_MARKDOWN,
            "document.grounded.md",
            result["grounded_markdown"].encode(),
            "text/markdown",
            None,
        ),
        (
            ArtifactType.CONTEXT_JSON,
            "document.context.json",
            json.dumps(result["context"], ensure_ascii=False, indent=2).encode(),
            "application/json",
            None,
        ),
        (
            ArtifactType.STRUCTURED_BLOCKS,
            "document.blocks.json",
            structured_document.model_dump_json(indent=2).encode(),
            "application/json",
            None,
        ),
        (
            ArtifactType.SETTINGS,
            "settings.json",
            settings_data,
            "application/json",
            None,
        ),
        (
            ArtifactType.DIAGNOSTICS,
            "diagnostics.json",
            aggregate_diagnostics,
            "application/json",
            None,
        ),
    ]
    if parse_settings.segment_documents:
        manifest = {
            "schema_version": "paperplane-subdocuments/v1",
            "source_filename": job.original_filename,
            "source_sha256": job.source_sha256,
            "complete": not any(segment.missing_pages for segment in segments),
            "subdocuments": [
                {"id": record.id, **segment.model_dump(mode="json")}
                for record, segment in zip(subdocument_records, segments, strict=True)
            ],
        }
        payloads.append(
            (
                ArtifactType.SUBDOCUMENT_MANIFEST,
                "subdocuments.manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
                "application/json",
                None,
            )
        )
    if domain_extraction is not None:
        payloads.append(
            (
                ArtifactType.DOMAIN_EXTRACTION,
                "document.extraction.json",
                domain_extraction.model_dump_json(indent=2).encode(),
                "application/json",
                None,
            )
        )
    if schema_snapshot:
        schema_document = _schema_document(
            schema_snapshot,
            source_filename=job.original_filename,
            source_sha256=job.source_sha256,
            instances=schema_instances,
        )
        payloads.append(
            (
                ArtifactType.SCHEMA_EXTRACTION,
                "document.schema-extraction.json",
                schema_document.model_dump_json(indent=2, by_alias=True).encode(),
                "application/json",
                None,
            )
        )
        payloads.extend(schema_table_payloads)

    try:
        data = await asyncio.to_thread(build_grounding_pdf, source, job.original_filename, layout)
        payloads.append(
            (ArtifactType.GROUNDING_PDF, "annotated.pdf", data, "application/pdf", None)
        )
    except Exception as exc:
        warnings.append(f"artifact:grounding_pdf:failed:{type(exc).__name__}")
    if await _finish_cancel_if_requested(sessions, job_id):
        return
    if parse_settings.searchable_pdf:
        try:
            data, pdf_warnings = await asyncio.to_thread(
                build_searchable_pdf, source, job.original_filename, layout
            )
            warnings.extend(f"artifact:searchable_pdf:{warning}" for warning in pdf_warnings)
            payloads.append(
                (ArtifactType.SEARCHABLE_PDF, "searchable.pdf", data, "application/pdf", None)
            )
        except Exception as exc:
            warnings.append(f"artifact:searchable_pdf:failed:{type(exc).__name__}")
        if await _finish_cancel_if_requested(sessions, job_id):
            return

    for region_id, path in result.get("figure_crops", {}).items():
        try:
            data = await asyncio.to_thread(Path(path).read_bytes)
            payloads.append(
                (ArtifactType.FIGURE, f"figures/{region_id}.png", data, "image/png", region_id)
            )
        except Exception as exc:
            warnings.append(f"artifact:figure:{region_id}:failed:{type(exc).__name__}")

    warnings = list(dict.fromkeys(warnings))
    warnings_data = json.dumps(warnings, ensure_ascii=False, indent=2).encode()
    payloads.append(
        (ArtifactType.WARNINGS, "warnings.json", warnings_data, "application/json", None)
    )
    if parse_settings.bundle:
        try:
            bundle_files = {filename: data for _, filename, data, _, _ in payloads}
            bundle_files[f"source/{job.original_filename}"] = source
            bundle = await asyncio.to_thread(build_bundle, bundle_files)
            payloads.append(
                (ArtifactType.BUNDLE, "document-bundle.zip", bundle, "application/zip", None)
            )
        except Exception as exc:
            warnings.append(f"artifact:bundle:failed:{type(exc).__name__}")

    if await _finish_cancel_if_requested(sessions, job_id):
        return

    warnings = list(dict.fromkeys(warnings))
    for index, payload in enumerate(payloads):
        if payload[0] == ArtifactType.WARNINGS:
            payloads[index] = (
                ArtifactType.WARNINGS,
                "warnings.json",
                json.dumps(warnings, ensure_ascii=False, indent=2).encode(),
                "application/json",
                None,
            )
            break

    run_id = uuid.uuid4().hex
    records = [_artifact(job_id, run_id, *payload) for payload in payloads]
    for record, payload in zip(records, payloads, strict=True):
        await asyncio.to_thread(store.write, record.relative_path, payload[2])
    for files in checkpoint_files.values():
        for path, data in files.values():
            await asyncio.to_thread(store.write, path, data)

    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        if job.cancel_requested:
            _apply_cancelled(job)
            await session.commit()
            return
        await session.execute(delete(Artifact).where(Artifact.job_id == job_id))
        await session.execute(delete(SubDocument).where(SubDocument.job_id == job_id))
        session.add_all(records)
        session.add_all(subdocument_records)
        for segment, record in zip(segments, subdocument_records, strict=True):
            if not segment.complete or segment.confidence < 0.8 or segment.warnings:
                await sync_grounded_review_case(
                    session,
                    job_id=job_id,
                    item_kind="subdocument",
                    item_key=f"subdocument:{segment.ordinal}",
                    original={"segment": segment.model_dump(mode="json"), "record_id": record.id},
                    failure_codes=list(segment.warnings) or ["segmentation_low_confidence"],
                    policy=job.quality_policy_snapshot,
                    page_number=segment.start_page,
                )
        for index, instance in enumerate(schema_instances):
            if not instance.complete or instance.validation_errors or instance.conflicts:
                await sync_grounded_review_case(
                    session,
                    job_id=job_id,
                    item_kind="schema_value",
                    item_key=f"schema:{index}",
                    original=instance.model_dump(mode="json"),
                    failure_codes=[item.code for item in instance.validation_errors]
                    or list(instance.warnings)
                    or ["schema_conflict"],
                    policy=job.quality_policy_snapshot,
                )
        diagnostic_by_page = {item.page_number: item for item in diagnostics}
        for page in job.pages:
            diagnostic = diagnostic_by_page.get(page.page_number)
            files = checkpoint_files.get(page.page_number)
            if diagnostic is None or files is None:
                if page.status != PageStatus.COMPLETED:
                    page.status = PageStatus.FAILED
                    page.error_code = page.error_code or "batch_failed"
                    page.error_message = page.error_message or "Page batch did not complete"
                continue
            page.status = PageStatus.COMPLETED
            page.stage = "completed"
            page.routing = parse_settings.input_mode
            page.layout_path = files["layout"][0]
            page.layout_sha256 = _sha256(files["layout"][1])
            page.diagnostics_path = files["diagnostics"][0]
            page.fingerprint = diagnostic.fingerprint
            page.quality_status = diagnostic.quality_status
            page.quality_score = (
                diagnostic.quality_score.overall if diagnostic.quality_score else None
            )
            page.repair_count = diagnostic.repair_count
            page.attempts = max(
                (len(item.attempts) for item in diagnostic.region_decisions), default=0
            )
            review = reviews.get(page.page_number) or reviews.get(str(page.page_number)) or {}
            page.duration_ms = review.get("latency_ms")
            page.warnings = [item for item in warnings if item.startswith(f"p{page.page_number}:")]
            await sync_page_review_cases(session, job_id, diagnostic, job.quality_policy_snapshot)
        job.completed_pages = sum(page.status == PageStatus.COMPLETED for page in job.pages)
        job.failed_pages = sum(page.status == PageStatus.FAILED for page in job.pages)
        job.warning_count = len(warnings)
        if domain_extraction is not None:
            job.detected_profile = domain_extraction.detected_profile
            job.profile_confidence = domain_extraction.classification_confidence
        job.segmentation_status = "completed" if parse_settings.segment_documents else "disabled"
        job.status = (
            JobStatus.COMPLETED_WITH_WARNINGS
            if warnings or job.failed_pages
            else JobStatus.COMPLETED
        )
        job.current_page = None
        job.completed_at = dt.datetime.now(dt.UTC)
        await session.commit()


async def _finalize_linked_evaluations(
    sessions: async_sessionmaker[AsyncSession], store: ObjectStore, job_id: str
) -> None:
    try:
        await finalize_evaluations_for_job(sessions, store, job_id)
    except Exception as exc:
        logger.info(
            "evaluation.finalization_failed",
            job_id=job_id,
            exception_type=type(exc).__name__,
        )


async def _terminalize(sessions, job_id: str, status: JobStatus, code: str, message: str) -> None:
    async with sessions() as session:
        job = await session.get(ParseJob, job_id)
        if job is None or job.status == JobStatus.CANCELLED:
            return
        if job.cancel_requested:
            status, code, message = JobStatus.CANCELLED, "", ""
        job.status = status
        job.error_code = code or None
        job.error_message = message or None
        job.current_page = None
        job.completed_at = None if status == JobStatus.PAUSED else dt.datetime.now(dt.UTC)
        await session.commit()


async def _publish_page_progress(
    sessions: async_sessionmaker[AsyncSession],
    job_id: str,
    page_number: int,
    event: str,
) -> None:
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        job.current_page = page_number
        checkpoint = next((page for page in job.pages if page.page_number == page_number), None)
        if checkpoint is not None:
            checkpoint.stage = event
            if event in {"page_parsed", "page_refined"}:
                checkpoint.status = PageStatus.PROCESSING
        if event == "page_refined":
            job.completed_pages = sum(page.stage == "page_refined" for page in job.pages)
        await session.commit()


async def _unload_local_models(
    runtime: ParserRuntime,
    models: set[str],
    *,
    report_resident: bool = False,
) -> list[str]:
    warnings: list[str] = []
    for model in sorted(models):
        try:
            await GLMOCRAdapter(runtime.client, model).unload()
        except GLMOCRUnavailable:
            warnings.append(f"ollama:{model}:unload_failed")
    if not report_resident:
        return warnings
    try:
        response = await runtime.client.get("/api/ps")
        response.raise_for_status()
        body = response.json()
        values = body.get("models", []) if isinstance(body, dict) else []
        remaining = sorted(
            {
                str(item.get("name") or item.get("model"))
                for item in values
                if isinstance(item, dict) and (item.get("name") or item.get("model"))
            }
        )
        if remaining:
            warnings.append(f"gpu:ollama_models_still_loaded:{','.join(remaining[:5])}")
    except (ValueError, TypeError, httpx.HTTPError):
        warnings.append("gpu:ollama_residency_check_failed")
    return warnings


def _apply_cancelled(job: ParseJob) -> None:
    job.status = JobStatus.CANCELLED
    job.current_page = None
    job.completed_at = dt.datetime.now(dt.UTC)


async def _finish_cancel_if_requested(sessions, job_id: str) -> bool:
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None or not job.cancel_requested:
            return False
        _apply_cancelled(job)
        await session.commit()
        return True


async def _publish_stage(sessions, job_id: str, node: str) -> bool:
    stages = {
        "ingest_and_render": "ingesting",
        "visual_segmentation": "segmenting",
        "zone_processing": "processing",
        "layout_stitching": "stitching",
        "self_reflection": "reflecting",
        "finalize": "finalizing",
    }
    async with sessions() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return False
        if job.cancel_requested:
            _apply_cancelled(job)
            await session.commit()
            return True
        job.status = (
            JobStatus.ASSEMBLING
            if node in {"layout_stitching", "finalize"}
            else JobStatus.PROCESSING
        )
        for page in job.pages:
            page.status = PageStatus.PROCESSING
            page.stage = stages[node]
        await session.commit()
        return False
