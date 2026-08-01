"""Stateless page task execution and idempotent V2 document assembly."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import settings
from app.logging_setup import get_logger
from app.models.db_models import Artifact, ParseJob, V2PageTask
from app.models.enums import JobStatus, PageStatus
from app.services.agentic.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    BlockType,
    NormalizedBox,
    assemble_parse_response,
)
from app.services.agentic.supervisor import AdaptiveDocumentSupervisor
from app.services.parsing.ingest import render_page
from app.services.parsing.openai_document import OpenAIUsage
from app.services.parsing.review_cases import sync_grounded_review_case
from app.services.parsing.storage import ObjectStore
from app.services.parsing.v2_annotations import build_annotated_pdf
from app.services.parsing.v2_cache import PageResultCache, page_cache_key
from app.services.parsing.v2_contracts import (
    DocumentItem,
    DocumentPage,
    DocumentResult,
    ItemVerification,
    MarkdownSpan,
    PageDimensions,
    ProcessingMode,
    QualitySummary,
    SchemaExtraction,
    SourceDocument,
    VerificationStatus,
    mode_policy,
)
from app.services.parsing.v2_cost import ModelRates, calculate_usage_cost
from app.services.parsing.v2_pipeline import PageResult, V2PageProcessor
from app.services.parsing.v2_schema_extraction import V2SchemaExtractor
from app.services.parsing.v2_segmentation import build_document_splits
from app.services.v2_tasks import V2TaskLeases

ASSEMBLY_MAX_ATTEMPTS = 3
logger = get_logger("app.services.v2_worker")
_ANCHOR_LINE = re.compile(r'^<a id="[^"]+"></a>\r?\n(?:\r?\n)?', re.MULTILINE)
_BLOCK_TYPE_MAP: dict[str, tuple[BlockType, str | None]] = {
    "title": ("text", "title"),
    "heading": ("text", "heading"),
    "text": ("text", None),
    "list": ("text", "list"),
    "checkbox": ("text", "checkbox"),
    "table": ("table", None),
    "table_cell": ("text", "table_cell"),
    "form_field": ("text", "form_field"),
    "figure": ("figure", None),
    "chart": ("figure", "chart"),
    "header": ("marginalia", "header"),
    "footer": ("marginalia", "footer"),
}


class IncompletePageSetError(RuntimeError):
    pass


class AgenticSupervisor(Protocol):
    async def run_document(
        self,
        pages: Sequence[Mapping[str, object]],
        *,
        model: str,
        thread_id: str,
    ) -> dict[str, object]: ...


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_clean_markdown(page_results: list[PageResult]) -> str:
    pages = [
        _ANCHOR_LINE.sub("", result.markdown).strip()
        for result in sorted(page_results, key=lambda item: item.page_number)
    ]
    return "\n\n<!-- PAGE BREAK -->\n\n".join(pages)


def _document_page(result: PageResult) -> DocumentPage:
    items: list[DocumentItem] = []
    cursor = 0
    for chunk in result.chunks:
        start = result.markdown.find(chunk.markdown.strip(), cursor)
        if start < 0:
            start = result.markdown.find(chunk.markdown.strip())
        if start < 0:
            start = end = 0
        else:
            end = start + len(chunk.markdown.strip())
            cursor = end
        items.append(
            DocumentItem(
                id=chunk.id,
                order=chunk.order,
                type=chunk.type,
                text=chunk.text,
                markdown_span=MarkdownSpan(start=start, end=end),
                parent_id=chunk.parent_id,
                grounding=chunk.grounding,
                verification=ItemVerification(
                    status=chunk.verification_status,
                    model=chunk.source_model,
                    pass_name=chunk.source_pass,
                    warnings=chunk.warnings,
                ),
            )
        )
    statuses = {item.verification.status for item in items}
    page_status = (
        VerificationStatus.UNRESOLVED
        if VerificationStatus.UNRESOLVED in statuses
        else VerificationStatus.CANDIDATE
        if VerificationStatus.CANDIDATE in statuses
        else VerificationStatus.VERIFIED
    )
    return DocumentPage(
        number=result.page_number,
        dimensions=PageDimensions(
            width=result.width, height=result.height, unit=result.source_unit
        ),
        verification_status=page_status,
        markdown=result.markdown,
        warnings=[warning for chunk in result.chunks for warning in chunk.warnings],
        items=items,
    )


def _default_agentic_supervisor() -> AdaptiveDocumentSupervisor:
    async def assess(page: Mapping[str, object]) -> Mapping[str, object]:
        result = page["page_result"]
        if not isinstance(result, PageResult):
            raise TypeError("agentic page payload must contain a PageResult")
        types = {chunk.type for chunk in result.chunks}
        roles = ["text_fidelity", "hierarchy_order"]
        if types & {"table", "table_cell"}:
            roles.append("tables")
        if types & {"form_field", "checkbox"}:
            roles.append("forms")
        if types & {"figure", "chart"}:
            roles.append("visual")
        if any(chunk.warnings for chunk in result.chunks):
            roles.append("special_marks")
        return {"roles": roles}

    async def specialize(page: Mapping[str, object], role: str, wave: int) -> Mapping[str, object]:
        result = page["page_result"]
        if not isinstance(result, PageResult):
            raise TypeError("agentic page payload must contain a PageResult")
        return {"summary": f"{role} assessed {len(result.chunks)} grounded blocks"}

    async def critique(
        page: Mapping[str, object], actions: Sequence[Mapping[str, object]], wave: int
    ) -> Mapping[str, object]:
        result = page["page_result"]
        if not isinstance(result, PageResult):
            raise TypeError("agentic page payload must contain a PageResult")
        unresolved = any(
            chunk.verification_status == VerificationStatus.UNRESOLVED for chunk in result.chunks
        )
        return {"accepted": not unresolved, "request_roles": []}

    return AdaptiveDocumentSupervisor(
        assessor=assess,
        specialist=specialize,
        critic=critique,
    )


def _normalised_box(result: PageResult, chunk: Any) -> NormalizedBox:
    if chunk.grounding:
        box = chunk.grounding[0].box
        return NormalizedBox(left=box.left, top=box.top, right=box.right, bottom=box.bottom)
    return NormalizedBox(left=0, top=0, right=1, bottom=1)


def _atomic_lines(markdown: str, box: NormalizedBox) -> list[AtomicLineInput]:
    return [AtomicLineInput(text=line, box=box) for line in markdown.splitlines() if line.strip()]


def _agentic_page(result: PageResult) -> AgenticPageInput:
    chunks = sorted(result.chunks, key=lambda item: item.order)
    children_by_parent: dict[str, list[Any]] = {}
    for chunk in chunks:
        if chunk.type == "table_cell" and chunk.parent_id:
            children_by_parent.setdefault(chunk.parent_id, []).append(chunk)

    blocks: list[AgenticBlockInput] = []
    nested_ids: set[str] = set()
    for chunk in chunks:
        if chunk.id in nested_ids:
            continue
        block_type, semantic_role = _BLOCK_TYPE_MAP[chunk.type]

        box = _normalised_box(result, chunk)
        table_cells: list[AgenticBlockInput] = []
        if block_type == "table":
            cursor = 0
            for cell_index, cell in enumerate(children_by_parent.get(chunk.id, [])):
                start = chunk.markdown.find(cell.markdown, cursor)
                if start < 0:
                    continue
                cursor = start + len(cell.markdown)
                nested_ids.add(cell.id)
                cell_box = _normalised_box(result, cell)
                table_cells.append(
                    AgenticBlockInput(
                        type="table_cell",
                        markdown=cell.markdown,
                        box=cell_box,
                        atomic_lines=_atomic_lines(cell.markdown, cell_box),
                        row=0,
                        col=cell_index,
                    )
                )
        blocks.append(
            AgenticBlockInput(
                type=block_type,
                markdown=chunk.markdown,
                box=box,
                semantic_role=semantic_role,
                atomic_lines=_atomic_lines(chunk.markdown, box),
                table_cells=table_cells,
            )
        )
    return AgenticPageInput(page_number=result.page_number, blocks=blocks)


class V2PageTaskRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        store: ObjectStore,
        processor: V2PageProcessor,
        leases: V2TaskLeases,
        *,
        extractor: V2SchemaExtractor | None = None,
        agentic_supervisor: AgenticSupervisor | None = None,
    ) -> None:
        self.sessions = sessions
        self.store = store
        self.processor = processor
        self.leases = leases
        self.extractor = extractor
        self.agentic_supervisor = agentic_supervisor

    async def run(self, task: V2PageTask, *, owner: str) -> None:
        async with self.sessions() as session:
            job = await session.scalar(
                select(ParseJob)
                .where(ParseJob.id == task.job_id)
                .options(selectinload(ParseJob.pages))
                .with_for_update()
            )
            if job is None:
                await self.leases.fail(task.id, owner, error_message="job_not_found")
                return
            if job.cancel_requested:
                await self._skip_cancelled_task(session, job, task)
                return
            job.status = JobStatus.PROCESSING
            job.current_page = task.page_number
            checkpoint = next(page for page in job.pages if page.page_number == task.page_number)
            checkpoint.status = PageStatus.PROCESSING
            checkpoint.stage = "openai_page_draft"
            await session.commit()
            source_path = job.source_path
            filename = job.original_filename
            source_path = job.source_path
            source_sha256 = job.source_sha256
            mode = ProcessingMode(job.settings.get("mode", "balanced"))
            api_family = job.settings.get("api_family")
            agentic_model = str(job.settings.get("model", "paperplane-ade-latest"))

        source = await asyncio.to_thread(self.store.read, source_path)
        policy = mode_policy(mode)
        rendered = await asyncio.to_thread(
            render_page, source, filename, task.page_number, policy.base_dpi
        )
        cache = PageResultCache(self.store)
        cache_key = page_cache_key(
            rendered.image_png,
            mode=f"{mode.value}:p{task.page_number}",
            prompt_version="v8",
        )
        result = await asyncio.to_thread(cache.get, cache_key)
        if result is None:
            result = await self.processor.process_page(
                source=source,
                filename=filename,
                source_sha256=source_sha256,
                page=rendered,
                mode=mode,
            )
            await asyncio.to_thread(cache.put, cache_key, result)
        result_path = f"jobs-v2/{task.job_id}/pages/p{task.page_number:04d}.json"
        await asyncio.to_thread(
            self.store.write, result_path, result.model_dump_json(indent=2).encode()
        )
        for evidence_id, data in result.evidence_artifacts.items():
            path = f"jobs-v2/{task.job_id}/evidence/{_sha256(evidence_id.encode())[:20]}.png"
            await asyncio.to_thread(self.store.write, path, data)

        if api_family == "agentic_v2":
            supervisor = self.agentic_supervisor
            if supervisor is None:
                supervisor = _default_agentic_supervisor()
                self.agentic_supervisor = supervisor
            supervised = await supervisor.run_document(
                [{"page_number": task.page_number, "page_result": result}],
                model=agentic_model,
                thread_id=f"{task.job_id}:page:{task.page_number}",
            )
            trace_path = f"jobs-v2/{task.job_id}/pages/p{task.page_number:04d}.trace.json"
            await asyncio.to_thread(
                self.store.write,
                trace_path,
                json.dumps(supervised, indent=2).encode(),
            )

        await self.leases.complete(
            task.id,
            owner,
            result_path=result_path,
            warnings=[warning for chunk in result.chunks for warning in chunk.warnings],
        )
        await self._assemble_with_retries(task.job_id)

    async def _skip_cancelled_task(
        self, session: AsyncSession, job: ParseJob, task: V2PageTask
    ) -> None:
        """A cancel landed before this task's provider work started — mark it
        cancelled rather than processed, and finalize the job once no
        queued/leased tasks remain. In-flight tasks (already past this check)
        are not aborted; see _assemble_if_complete for the assembly-side guard.
        """
        db_task = await session.get(V2PageTask, task.id)
        if db_task is not None:
            db_task.status = "cancelled"
            db_task.lease_owner = None
            db_task.lease_expires_at = None
        remaining = await session.scalar(
            select(func.count())
            .select_from(V2PageTask)
            .where(V2PageTask.job_id == job.id, V2PageTask.status.in_(("queued", "leased")))
        )
        finalized = False
        if not remaining and job.status != JobStatus.CANCELLED:
            job.status = JobStatus.CANCELLED
            job.current_page = None
            job.completed_at = dt.datetime.now(dt.UTC)
            finalized = True
        await session.commit()
        logger.info(
            "v2_page_task_skipped_cancelled",
            job_id=job.id,
            page_number=task.page_number,
            job_finalized=finalized,
        )

    async def _assemble_with_retries(self, job_id: str) -> None:
        for attempt in range(1, ASSEMBLY_MAX_ATTEMPTS + 1):
            try:
                await self._assemble_if_complete(job_id)
                return
            except Exception as exc:
                error_type = type(exc).__name__
                if attempt < ASSEMBLY_MAX_ATTEMPTS:
                    logger.warning(
                        "v2_assembly_retry",
                        job_id=job_id,
                        attempt=attempt,
                        error_type=error_type,
                    )
                    continue
                logger.error(
                    "v2_assembly_failed",
                    job_id=job_id,
                    attempt=attempt,
                    error_type=error_type,
                )
                await self._fail_assembly(job_id, error_type)

    async def _fail_assembly(self, job_id: str, error_type: str) -> None:
        async with self.sessions() as session:
            job = await session.scalar(
                select(ParseJob).where(ParseJob.id == job_id).with_for_update()
            )
            if job is None or job.status == JobStatus.CANCELLED:
                return
            tasks = list(
                await session.scalars(
                    select(V2PageTask)
                    .where(V2PageTask.job_id == job_id)
                    .order_by(V2PageTask.page_number)
                )
            )
            job.status = JobStatus.FAILED
            job.current_page = None
            job.completed_pages = sum(task.status == "completed" for task in tasks)
            job.failed_pages = sum(task.status == "failed" for task in tasks)
            job.error_code = "assembly_failed"
            job.error_message = (
                f"Assembly failed after {ASSEMBLY_MAX_ATTEMPTS} attempts: {error_type}"[:240]
            )
            await session.commit()

    async def _assemble_if_complete(self, job_id: str) -> None:
        async with self.sessions() as session:
            tasks = list(
                await session.scalars(
                    select(V2PageTask)
                    .where(V2PageTask.job_id == job_id)
                    .order_by(V2PageTask.page_number)
                )
            )
            if not tasks or any(
                task.status != "completed" or not task.result_path for task in tasks
            ):
                return
            job = await session.scalar(
                select(ParseJob)
                .where(ParseJob.id == job_id)
                .options(selectinload(ParseJob.artifacts), selectinload(ParseJob.pages))
            )
            if job is None:
                return
            if job.cancel_requested or job.status == JobStatus.CANCELLED:
                # Every page finished (it was already in flight when cancel
                # landed — see _skip_cancelled_task), but assembly itself is
                # new work: extraction calls, PDF annotation. Cancellation
                # blocks that even though the pages themselves ran to completion.
                if job.status != JobStatus.CANCELLED:
                    job.status = JobStatus.CANCELLED
                    job.current_page = None
                    job.completed_pages = sum(task.status == "completed" for task in tasks)
                    job.completed_at = dt.datetime.now(dt.UTC)
                    await session.commit()
                    logger.info("v2_job_cancelled_before_assembly", job_id=job_id)
                return
            expected_pages = list(range(1, job.page_count + 1))
            if [task.page_number for task in tasks] != expected_pages:
                raise IncompletePageSetError("page tasks do not match job page_count")
            job.status = JobStatus.ASSEMBLING
            await session.commit()
            filename = job.original_filename
            source_path = job.source_path
            source_mime = job.source_mime
            source_sha256 = job.source_sha256
            page_count = job.page_count
            segment_documents = bool(job.settings.get("segment_documents", True))
            mode = ProcessingMode(job.settings.get("mode", "balanced"))
            api_family = job.settings.get("api_family")
            agentic_model = str(job.settings.get("model", "paperplane-ade-latest"))
            extraction_schema = job.extraction_schema_snapshot

        page_results = [
            PageResult.model_validate_json(
                await asyncio.to_thread(self.store.read, task.result_path)
            )
            for task in tasks
            if task.result_path
        ]
        if [result.page_number for result in page_results] != expected_pages:
            raise IncompletePageSetError("page results do not match job page_count")
        chunks = [chunk for result in page_results for chunk in result.chunks]
        clean_markdown = build_clean_markdown(page_results)
        usage: dict[str, Any] = {
            "input_tokens": sum(result.input_tokens for result in page_results),
            "output_tokens": sum(result.output_tokens for result in page_results),
            "cached_input_tokens": sum(result.cached_input_tokens for result in page_results),
            "cache_write_tokens": sum(result.cache_write_tokens for result in page_results),
        }
        model_usage: dict[str, OpenAIUsage] = {}
        for result in page_results:
            for model, item in result.model_usage.items():
                aggregate = model_usage.setdefault(model, OpenAIUsage())
                aggregate.input_tokens += item.input_tokens
                aggregate.output_tokens += item.output_tokens
                aggregate.cached_input_tokens += item.cached_input_tokens
                aggregate.cache_write_tokens += item.cache_write_tokens
        extraction = {}
        structured_data = None
        if extraction_schema and self.extractor is not None:
            outcome = await self.extractor.extract(
                markdown=clean_markdown,
                chunks=chunks,
                user_schema=extraction_schema["json_schema"],
                source_sha256=source_sha256,
                reasoning_effort="high" if mode == ProcessingMode.AUDIT else "medium",
            )
            extraction = outcome.fields
            structured_data = outcome.structured_data
            usage["input_tokens"] += outcome.usage.input_tokens
            usage["output_tokens"] += outcome.usage.output_tokens
            usage["cached_input_tokens"] += outcome.usage.cached_input_tokens
            usage["cache_write_tokens"] += outcome.usage.cache_write_tokens
            aggregate = model_usage.setdefault("gpt-5.6-terra", OpenAIUsage())
            aggregate.input_tokens += outcome.usage.input_tokens
            aggregate.output_tokens += outcome.usage.output_tokens
            aggregate.cached_input_tokens += outcome.usage.cached_input_tokens
            aggregate.cache_write_tokens += outcome.usage.cache_write_tokens
        rates = {
            "gpt-5.6-luna": ModelRates(
                input_per_million=settings.luna_input_per_million,
                cached_input_per_million=settings.luna_cached_input_per_million,
                output_per_million=settings.luna_output_per_million,
            ),
            "gpt-5.6-terra": ModelRates(
                input_per_million=settings.terra_input_per_million,
                cached_input_per_million=settings.terra_cached_input_per_million,
                output_per_million=settings.terra_output_per_million,
            ),
        }
        pricing_configured = any(
            rate.input_per_million or rate.cached_input_per_million or rate.output_per_million
            for rate in rates.values()
        )
        cost = calculate_usage_cost(model_usage, rates)
        usage.update(
            {
                "by_model": {
                    model: item.model_dump(mode="json") for model, item in model_usage.items()
                },
                "pricing_version": settings.openai_pricing_version,
                "pricing_configured": pricing_configured,
                "total_usd": cost.total_usd if pricing_configured else None,
                "cost_by_model": cost.by_model if pricing_configured else {},
            }
        )
        unresolved_items = sum(
            chunk.verification_status == VerificationStatus.UNRESOLVED for chunk in chunks
        )
        extraction_unresolved = sum(field.status == "unresolved" for field in extraction.values())
        candidate = sum(
            chunk.verification_status == VerificationStatus.CANDIDATE for chunk in chunks
        )
        verified = sum(chunk.verification_status == VerificationStatus.VERIFIED for chunk in chunks)
        warning_count = unresolved_items + candidate + extraction_unresolved
        trace_payload: dict[str, object] | None = None
        if api_family == "agentic_v2":
            trace_pages: list[dict[str, object]] = []
            trace_events: list[dict[str, object]] = []
            for result in page_results:
                trace_path = f"jobs-v2/{job_id}/pages/p{result.page_number:04d}.trace.json"
                page_trace = json.loads(await asyncio.to_thread(self.store.read, trace_path))
                page_results_trace = page_trace.get("results", [])
                trace_pages.append(
                    {
                        "page_number": result.page_number,
                        "result": page_results_trace[0] if page_results_trace else {},
                    }
                )
                trace_events.extend(page_trace.get("trace", []))
            trace_payload = {
                "job_id": job_id,
                "model": agentic_model,
                "pages": trace_pages,
                "events": trace_events,
            }
            parse_response = assemble_parse_response(
                document_id=job_id,
                job_id=job_id,
                model=agentic_model,
                pages=[_agentic_page(result) for result in page_results],
            )
            document_json = parse_response.model_dump_json(indent=2).encode()
            output_markdown = parse_response.markdown
        else:
            document = DocumentResult(
                source=SourceDocument(
                    filename=filename,
                    sha256=source_sha256,
                    mime_type=source_mime,
                    page_count=page_count,
                ),
                status="completed_with_warnings" if warning_count else "completed",
                quality_summary=QualitySummary(
                    verified_items=verified,
                    candidate_items=candidate,
                    unresolved_items=unresolved_items,
                    warning_count=warning_count,
                ),
                pages=[_document_page(result) for result in page_results],
                splits=build_document_splits(
                    chunks, page_count=page_count, enabled=segment_documents
                ),
                extraction=(
                    SchemaExtraction(data=structured_data, fields=extraction)
                    if extraction_schema
                    else None
                ),
                usage=usage,
                processing={
                    "mode": mode.value,
                    "draft_model": "gpt-5.6-luna",
                    "verification_model": "gpt-5.6-terra",
                },
            )
            document_json = document.model_dump_json(indent=2, by_alias=True).encode()
            output_markdown = clean_markdown
        source = await asyncio.to_thread(self.store.read, source_path)
        annotated_pdf = await asyncio.to_thread(build_annotated_pdf, source, filename, chunks)
        payloads = [
            (
                "markdown",
                "document.md",
                output_markdown.encode(),
                "text/markdown",
            ),
            (
                "json",
                "document.json",
                document_json,
                "application/json",
            ),
            (
                "annotated_pdf",
                "annotated.pdf",
                annotated_pdf,
                "application/pdf",
            ),
        ]
        if trace_payload is not None:
            payloads.append(
                (
                    "agent_trace",
                    "agent-trace.json",
                    json.dumps(trace_payload, indent=2).encode(),
                    "application/json",
                )
            )
        records: list[Artifact] = []
        for artifact_type, filename_out, data, mime_type in payloads:
            path = f"jobs-v2/{job_id}/{filename_out}"
            await asyncio.to_thread(self.store.write, path, data)
            records.append(
                Artifact(
                    id=uuid.uuid4().hex,
                    job_id=job_id,
                    type=artifact_type,
                    relative_path=path,
                    mime_type=mime_type,
                    size=len(data),
                    sha256=_sha256(data),
                )
            )

        async with self.sessions() as session:
            job = await session.get(ParseJob, job_id)
            if job is None:
                return
            await session.execute(delete(Artifact).where(Artifact.job_id == job_id))
            session.add_all(records)
            if api_family == "agentic_v2":
                for chunk in chunks:
                    if chunk.verification_status != VerificationStatus.UNRESOLVED:
                        continue
                    await sync_grounded_review_case(
                        session,
                        job_id=job_id,
                        item_kind="block",
                        item_key=chunk.id,
                        page_number=chunk.page,
                        original=chunk.model_dump(mode="json"),
                        failure_codes=chunk.warnings or ["unresolved_grounding"],
                        policy={"model": agentic_model},
                    )
            job.warning_count = warning_count
            job.quality_policy_snapshot = {
                "usage": usage,
                **(
                    {
                        "agentic": {
                            "model": agentic_model,
                            "trace_path": f"jobs-v2/{job_id}/agent-trace.json",
                        }
                    }
                    if trace_payload is not None
                    else {}
                ),
            }
            job.status = JobStatus.COMPLETED_WITH_WARNINGS if warning_count else JobStatus.COMPLETED
            job.current_page = None
            job.completed_pages = page_count
            job.failed_pages = 0
            job.completed_at = dt.datetime.now(dt.UTC)
            await session.commit()
