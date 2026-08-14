import hashlib
import json
from io import BytesIO

import fitz
import pytest
from PIL import Image
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, selectinload

import app.services.v2_worker as v2_worker
from app.models.db_models import Artifact, Base, PageCheckpoint, ParseJob, ReviewCase, V2PageTask
from app.services.parsing.contracts import BoundingBox
from app.services.parsing.ingest import render_page
from app.services.parsing.openai_document import OpenAIUsage
from app.services.parsing.v2_cache import PageResultCache, page_cache_key
from app.services.parsing.v2_contracts import (
    ExtractionField,
    GroundedChunk,
    Grounding,
    GroundingMethod,
    ProcessingMode,
    VerificationStatus,
    mode_policy,
)
from app.services.parsing.v2_pipeline import PageResult
from app.services.parsing.v2_schema_extraction import ExtractionOutcome
from app.services.v2_tasks import V2TaskLeases
from app.services.v2_worker import V2PageTaskRunner


class _Store:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def write(self, path: str, data: bytes) -> str:
        self.values[path] = data
        return path

    def read(self, path: str) -> bytes:
        return self.values[path]

    def delete_tree(self, path: str) -> None:
        raise NotImplementedError


class _Processor:
    async def process_page(self, **kwargs) -> PageResult:
        page = kwargs["page"]
        chunk = GroundedChunk(
            id=f"p{page.page_number:04d}-c0001",
            page=page.page_number,
            order=1,
            type="text",
            text="Invoice Number INV-42",
            markdown="Invoice Number INV-42",
            grounding=[
                Grounding(
                    page=page.page_number,
                    box=BoundingBox(left=0.1, top=0.1, right=0.8, bottom=0.2),
                    method=GroundingMethod.VISION_REFINED,
                    source_box=(10, 10, 80, 20),
                    source_unit="image_pixels",
                    evidence_artifact_id="page-evidence",
                )
            ],
            verification_status=VerificationStatus.VERIFIED,
            source_model="gpt-5.6-terra",
            source_pass="crop_verification",
        )
        return PageResult(
            page_number=page.page_number,
            width=page.width,
            height=page.height,
            source_unit="image_pixels",
            chunks=[chunk],
            markdown=chunk.markdown,
            input_tokens=100,
            output_tokens=10,
            cached_input_tokens=50,
        )


class _CountingProcessor(_Processor):
    def __init__(self) -> None:
        self.calls = 0

    async def process_page(self, **kwargs) -> PageResult:
        self.calls += 1
        return await super().process_page(**kwargs)


class _Extractor:
    async def extract(self, **kwargs) -> ExtractionOutcome:
        return ExtractionOutcome(
            fields={
                "invoice_number": ExtractionField(
                    value="INV-42",
                    status="grounded",
                    citations=["p0001-c0001"],
                )
            },
            structured_data={"invoice_number": "INV-42"},
            usage=OpenAIUsage(input_tokens=20, output_tokens=5),
        )


class _Supervisor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def run_document(self, pages, *, model: str, thread_id: str) -> dict:
        self.calls.append({"pages": pages, "model": model, "thread_id": thread_id})
        page_number = int(pages[0]["page_number"])
        return {
            "results": [
                {
                    "page_number": page_number,
                    "accepted": True,
                    "waves_completed": 1,
                    "specialist_calls": 1,
                    "stop_reason": "accepted",
                    "actions": [{"role": "text_fidelity", "summary": "verified"}],
                }
            ],
            "trace": [
                {
                    "page_number": page_number,
                    "action": "verdict",
                    "agent": "terra_critic",
                    "model": "gpt-5.6-terra",
                    "summary": "accepted",
                    "wave": 1,
                }
            ],
        }


class _UnresolvedProcessor(_Processor):
    async def process_page(self, **kwargs) -> PageResult:
        result = await super().process_page(**kwargs)
        result.chunks[0].verification_status = VerificationStatus.UNRESOLVED
        result.chunks[0].warnings = ["low_visual_confidence"]
        return result


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


def test_clean_markdown_is_human_readable_and_page_delimited() -> None:
    pages = [
        PageResult(
            page_number=1,
            chunks=[],
            markdown='<a id="p0001-c0001"></a>\n\n# First page',
        ),
        PageResult(
            page_number=2,
            chunks=[],
            markdown='<a id="p0002-c0001"></a>\n\nSecond page',
        ),
    ]

    assert v2_worker.build_clean_markdown(pages) == (
        "# First page\n\n<!-- PAGE BREAK -->\n\nSecond page"
    )


def test_document_items_for_parented_chunks_have_markdown_spans() -> None:
    heading = GroundedChunk(
        id="p0001-c0001",
        page=1,
        order=1,
        type="heading",
        text="Shipping Instructions",
        markdown="## Shipping Instructions",
        source_model="gpt-5.6-terra",
        source_pass="page_reconciliation",
    )
    body = GroundedChunk(
        id="p0001-c0002",
        page=1,
        order=2,
        type="text",
        text="Send samples by overnight courier.",
        markdown="Send samples by overnight courier.",
        parent_id=heading.id,
        source_model="gpt-5.6-terra",
        source_pass="page_reconciliation",
    )
    result = PageResult(
        page_number=1,
        chunks=[heading, body],
        markdown=f"{heading.markdown}\n\n{body.markdown}",
    )

    page = v2_worker._document_page(result)

    assert page.items[1].parent_id == heading.id
    assert page.items[1].markdown_span.start > 0
    assert page.items[1].markdown_span.end > page.items[1].markdown_span.start


async def _leased_runner(
    processor: _Processor,
    *,
    job_settings: dict | None = None,
    supervisor: _Supervisor | None = None,
):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _Store()
    source = _png()
    store.write("jobs-v2/job/source.png", source)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=len(source),
                source_sha256=hashlib.sha256(source).hexdigest(),
                page_count=1,
                status="queued",
                settings=job_settings or {"mode": "balanced", "segment_documents": True},
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)
    task = await leases.claim("worker-1", lease_seconds=30)
    assert task is not None
    return (
        engine,
        sessions,
        V2PageTaskRunner(
            sessions,
            store,
            processor,
            leases,
            agentic_supervisor=supervisor,
        ),
        task,
    )


async def test_agentic_job_assembles_dpt_contract_trace_and_annotated_pdf() -> None:
    supervisor = _Supervisor()
    engine, sessions, runner, task = await _leased_runner(
        _Processor(),
        job_settings={
            "api_family": "agentic_v2",
            "model": "paperplane-ade-latest",
            "mode": "balanced",
        },
        supervisor=supervisor,
    )

    await runner.run(task, owner="worker-1")

    store = runner.store
    async with sessions() as session:
        job = await session.scalar(
            select(ParseJob).where(ParseJob.id == "job").options(selectinload(ParseJob.artifacts))
        )
        assert job is not None and job.status == "completed"
        assert [artifact.type for artifact in job.artifacts] == [
            "markdown",
            "json",
            "annotated_pdf",
            "audit_manifest",
            "evidence_bundle",
            "agent_trace",
        ]

    assert supervisor.calls[0]["model"] == "paperplane-ade-latest"
    assert supervisor.calls[0]["thread_id"] == "job:page:1"
    assert supervisor.calls[0]["pages"][0]["page_number"] == 1
    document = json.loads(store.values["jobs-v2/job/document.json"])
    assert document["metadata"]["model"] == "paperplane-ade-latest"
    assert document["metadata"]["range_units"] == "unicode_codepoints"
    assert document["structure"]["children"][0]["children"][0]["type"] == "text"
    assert document["markdown"] == store.values["jobs-v2/job/document.md"].decode()
    trace = json.loads(store.values["jobs-v2/job/agent-trace.json"])
    assert trace["pages"][0]["result"]["stop_reason"] == "accepted"
    assert trace["events"][0]["agent"] == "terra_critic"
    annotated = fitz.open(stream=store.values["jobs-v2/job/annotated.pdf"], filetype="pdf")
    try:
        assert annotated.page_count == 1
    finally:
        annotated.close()
    await engine.dispose()


async def test_agentic_unresolved_block_creates_review_case_without_pausing() -> None:
    engine, sessions, runner, task = await _leased_runner(
        _UnresolvedProcessor(),
        job_settings={
            "api_family": "agentic_v2",
            "model": "paperplane-ade-fast-latest",
            "mode": "balanced",
        },
    )

    await runner.run(task, owner="worker-1")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        review_case = await session.scalar(select(ReviewCase).where(ReviewCase.job_id == "job"))
        assert job is not None and job.status == "completed_with_warnings"
        assert job.warning_count == 1
        assert review_case is not None
        assert review_case.item_key == "p0001-c0001"
        assert review_case.failure_codes == ["low_visual_confidence"]
    await engine.dispose()


async def test_runner_persists_page_and_assembles_auditable_artifacts() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _Store()
    source = _png()
    store.write("jobs-v2/job/source.png", source)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=len(source),
                source_sha256=hashlib.sha256(source).hexdigest(),
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
                extraction_schema_snapshot={
                    "json_schema": {
                        "type": "object",
                        "properties": {"invoice_number": {"type": "string"}},
                        "required": ["invoice_number"],
                        "additionalProperties": False,
                    }
                },
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)
    task = await leases.claim("worker-1", lease_seconds=30)
    assert task is not None

    runner = V2PageTaskRunner(sessions, store, _Processor(), leases, extractor=_Extractor())
    await runner.run(task, owner="worker-1")

    async with sessions() as session:
        job = await session.scalar(
            select(ParseJob)
            .where(ParseJob.id == "job")
            .options(selectinload(ParseJob.artifacts), selectinload(ParseJob.pages))
        )
        assert job is not None
        assert job.status == "completed"
        assert job.completed_pages == 1
        assert job.current_page is None
        assert job.quality_policy_snapshot["usage"]["input_tokens"] == 120
        assert job.pages[0].layout_path == "jobs-v2/job/pages/p0001.json"
        assert [artifact.type for artifact in job.artifacts] == [
            "markdown",
            "json",
            "annotated_pdf",
            "audit_manifest",
            "evidence_bundle",
        ]
    document = json.loads(store.values["jobs-v2/job/document.json"])
    assert store.values["jobs-v2/job/document.md"] == b"Invoice Number INV-42"
    assert document["schema_version"] == "paperplane-document/v3"
    assert document["pages"][0]["items"][0]["grounding"][0]["method"] == "vision_refined"
    assert "chunks" not in document and "markdown" not in document
    assert document["splits"][0]["identifier"] == "INV-42"
    assert document["usage"]["cached_input_tokens"] == 50
    assert document["extraction"]["data"] == {"invoice_number": "INV-42"}
    assert document["extraction"]["fields"]["invoice_number"]["value"] == "INV-42"
    assert document["usage"]["input_tokens"] == 120
    audit_manifest = json.loads(store.values["jobs-v2/job/audit-manifest.json"])
    assert audit_manifest["schema_version"] == "paperplane-audit/v1"
    assert audit_manifest["pages"][0]["page_number"] == 1
    assert store.values["jobs-v2/job/evidence-bundle.zip"].startswith(b"PK")
    assert any(isinstance(item, Artifact) for item in job.artifacts)
    annotated = fitz.open(stream=store.values["jobs-v2/job/annotated.pdf"], filetype="pdf")
    try:
        assert annotated.page_count == 1
        assert "p0001-c0001" in annotated[0].get_text()
    finally:
        annotated.close()
    rendered = render_page(
        source, "scan.png", page_number=1, dpi=mode_policy(ProcessingMode.BALANCED).base_dpi
    )
    cache_path = PageResultCache.path(
        page_cache_key(rendered.image_png, mode="balanced:p1", prompt_version="v8")
    )
    assert cache_path in store.values
    await engine.dispose()


async def test_assembly_fails_when_page_task_set_has_a_gap() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _Store()
    source = _png()
    store.write("jobs-v2/job/source.png", source)
    result = await _Processor().process_page(
        page=type("Page", (), {"page_number": 1, "width": 100, "height": 100})()
    )
    result_path = "jobs-v2/job/pages/p0001.json"
    store.write(result_path, result.model_dump_json().encode())
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=len(source),
                source_sha256=hashlib.sha256(source).hexdigest(),
                page_count=2,
                status="processing",
                settings={"mode": "balanced", "segment_documents": True},
                pages=[
                    PageCheckpoint(page_number=1, status="completed"),
                    PageCheckpoint(page_number=2, status="pending"),
                ],
            )
        )
        session.add(
            V2PageTask(
                job_id="job",
                page_number=1,
                status="completed",
                result_path=result_path,
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    runner = V2PageTaskRunner(sessions, store, _Processor(), leases)

    await runner._assemble_with_retries("job")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == "failed"
        assert job.error_code == "assembly_failed"
        assert "IncompletePageSetError" in (job.error_message or "")
    assert "jobs-v2/job/document.md" not in store.values
    await engine.dispose()


async def test_checkpoint_persistence_failure_leaves_page_task_retryable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _Store()
    source = _png()
    store.write("jobs-v2/job/source.png", source)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=len(source),
                source_sha256=hashlib.sha256(source).hexdigest(),
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)
    task = await leases.claim("worker-1", lease_seconds=30)
    assert task is not None
    runner = V2PageTaskRunner(sessions, store, _Processor(), leases)

    def reject_completed_checkpoint(session: Session, flush_context, instances) -> None:
        if any(
            isinstance(item, PageCheckpoint) and item.status == "completed"
            for item in session.dirty
        ):
            raise RuntimeError("checkpoint persistence unavailable")

    event.listen(Session, "before_flush", reject_completed_checkpoint)
    try:
        with pytest.raises(RuntimeError, match="checkpoint persistence unavailable"):
            await runner.run(task, owner="worker-1")
        await leases.fail(task.id, "worker-1", error_message="RuntimeError")
    finally:
        event.remove(Session, "before_flush", reject_completed_checkpoint)

    async with sessions() as session:
        saved_task = await session.get(V2PageTask, task.id)
        assert saved_task is not None and saved_task.status == "queued" and saved_task.attempts == 1
    await engine.dispose()


async def test_assembly_retries_without_reprocessing_the_completed_page(monkeypatch) -> None:
    processor = _CountingProcessor()
    engine, sessions, runner, task = await _leased_runner(processor)
    original = v2_worker._document_page
    attempts = 0

    def fail_twice(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError("temporary assembly failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(v2_worker, "_document_page", fail_twice)
    await runner.run(task, owner="worker-1")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        saved_task = await session.get(V2PageTask, task.id)
        assert job is not None and job.status == "completed" and job.current_page is None
        assert saved_task is not None and saved_task.status == "completed"
    assert attempts == 3
    assert processor.calls == 1
    await engine.dispose()


async def test_assembly_terminal_failure_keeps_completed_page_task(monkeypatch) -> None:
    processor = _CountingProcessor()
    engine, sessions, runner, task = await _leased_runner(processor)
    attempts = 0

    def always_fail(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("assembly unavailable")

    monkeypatch.setattr(v2_worker, "_document_page", always_fail)
    await runner.run(task, owner="worker-1")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        saved_task = await session.get(V2PageTask, task.id)
        assert job is not None and job.status == "failed" and job.current_page is None
        assert job.completed_pages == 1 and job.failed_pages == 0
        assert job.error_code == "assembly_failed"
        assert job.error_message == "Assembly failed after 3 attempts: RuntimeError"
        assert saved_task is not None and saved_task.status == "completed"
    assert attempts == 3
    assert processor.calls == 1
    await engine.dispose()
