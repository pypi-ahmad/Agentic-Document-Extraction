"""Stateless page task execution and idempotent V2 document assembly."""

from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.db_models import Artifact, ParseJob, V2PageTask
from app.models.enums import JobStatus, PageStatus
from app.services.parsing.ingest import render_page
from app.services.parsing.openai_document import OpenAIUsage
from app.services.parsing.storage import ObjectStore
from app.services.parsing.v2_annotations import build_annotated_pdf
from app.services.parsing.v2_cache import PageResultCache, page_cache_key
from app.services.parsing.v2_contracts import (
    DocumentResult,
    ProcessingMode,
    VerificationStatus,
    mode_policy,
)
from app.services.parsing.v2_cost import ModelRates, calculate_usage_cost
from app.services.parsing.v2_pipeline import PageResult, V2PageProcessor
from app.services.parsing.v2_schema_extraction import V2SchemaExtractor
from app.services.parsing.v2_segmentation import build_document_splits
from app.services.v2_tasks import V2TaskLeases


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class V2PageTaskRunner:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        store: ObjectStore,
        processor: V2PageProcessor,
        leases: V2TaskLeases,
        *,
        extractor: V2SchemaExtractor | None = None,
    ) -> None:
        self.sessions = sessions
        self.store = store
        self.processor = processor
        self.leases = leases
        self.extractor = extractor

    async def run(self, task: V2PageTask, *, owner: str) -> None:
        async with self.sessions() as session:
            job = await session.scalar(
                select(ParseJob)
                .where(ParseJob.id == task.job_id)
                .options(selectinload(ParseJob.pages))
            )
            if job is None:
                await self.leases.fail(task.id, owner, error_message="job_not_found")
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

        source = await asyncio.to_thread(self.store.read, source_path)
        policy = mode_policy(mode)
        rendered = await asyncio.to_thread(
            render_page, source, filename, task.page_number, policy.base_dpi
        )
        cache = PageResultCache(self.store)
        cache_key = page_cache_key(
            rendered.image_png,
            mode=f"{mode.value}:p{task.page_number}",
            prompt_version="v2",
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

        await self.leases.complete(task.id, owner, result_path=result_path)
        async with self.sessions() as session:
            job = await session.scalar(
                select(ParseJob)
                .where(ParseJob.id == task.job_id)
                .options(selectinload(ParseJob.pages))
            )
            if job is None:
                return
            checkpoint = next(page for page in job.pages if page.page_number == task.page_number)
            checkpoint.status = PageStatus.COMPLETED
            checkpoint.stage = "page_complete"
            checkpoint.layout_path = result_path
            checkpoint.attempts = task.attempts
            checkpoint.warnings = [warning for chunk in result.chunks for warning in chunk.warnings]
            job.completed_pages = sum(page.status == PageStatus.COMPLETED for page in job.pages)
            job.current_page = None
            await session.commit()
        await self._assemble_if_complete(task.job_id)

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
            job.status = JobStatus.ASSEMBLING
            await session.commit()
            filename = job.original_filename
            source_path = job.source_path
            source_sha256 = job.source_sha256
            page_count = job.page_count
            segment_documents = bool(job.settings.get("segment_documents", True))
            mode = ProcessingMode(job.settings.get("mode", "balanced"))
            extraction_schema = job.extraction_schema_snapshot

        page_results = [
            PageResult.model_validate_json(
                await asyncio.to_thread(self.store.read, task.result_path)
            )
            for task in tasks
            if task.result_path
        ]
        chunks = [chunk for result in page_results for chunk in result.chunks]
        markdown = "\n\n".join(result.markdown for result in page_results)
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
                markdown=markdown,
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
        document = DocumentResult(
            source_filename=filename,
            source_sha256=source_sha256,
            page_count=page_count,
            markdown=markdown,
            chunks=chunks,
            splits=build_document_splits(chunks, page_count=page_count, enabled=segment_documents),
            extraction=extraction,
            usage=usage,
            metadata={
                "draft_model": "gpt-5.6-luna",
                "verification_model": "gpt-5.6-terra",
                "structured_data": structured_data,
            },
        )
        source = await asyncio.to_thread(self.store.read, source_path)
        annotated_pdf = await asyncio.to_thread(build_annotated_pdf, source, filename, chunks)
        payloads = [
            (
                "document_json",
                "document.json",
                document.model_dump_json(indent=2).encode(),
                "application/json",
            ),
            ("clean_markdown", "document.md", markdown.encode(), "text/markdown"),
            ("usage", "usage.json", json.dumps(usage, indent=2).encode(), "application/json"),
            ("annotated_pdf", "annotated.pdf", annotated_pdf, "application/pdf"),
        ]
        if structured_data is not None:
            extraction_data = json.dumps(
                {
                    "data": structured_data,
                    "fields": {
                        name: field.model_dump(mode="json") for name, field in extraction.items()
                    },
                },
                indent=2,
            ).encode()
            payloads.append(
                ("schema_extraction", "extraction.json", extraction_data, "application/json")
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
            unresolved = sum(
                chunk.verification_status == VerificationStatus.UNRESOLVED for chunk in chunks
            )
            unresolved += sum(field.status == "unresolved" for field in extraction.values())
            job.warning_count = unresolved
            job.quality_policy_snapshot = {"usage": usage}
            job.status = JobStatus.COMPLETED_WITH_WARNINGS if unresolved else JobStatus.COMPLETED
            job.completed_pages = page_count
            job.completed_at = dt.datetime.now(dt.UTC)
            await session.commit()
