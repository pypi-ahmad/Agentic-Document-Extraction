"""Cancellation semantics for the live V2 job pipeline.

Covers: claim() refuses work for a cancelled job, the runner skips
provider calls for a task claimed just as cancellation lands, assembly
(new work) is blocked even when every page already finished in flight,
and concurrent cancel requests can't corrupt job state.
"""

import asyncio
import hashlib
from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db_models import Base, PageCheckpoint, ParseJob
from app.services.v2_tasks import V2TaskLeases
from app.services.v2_worker import V2PageTaskRunner


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


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
    def __init__(self) -> None:
        self.calls = 0

    async def process_page(self, **kwargs):
        self.calls += 1
        raise AssertionError("provider work must not run for a cancelled job's task")


async def test_claim_skips_queued_tasks_belonging_to_a_cancelled_job() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status="cancelling",
                cancel_requested=True,
                settings={"mode": "balanced"},
            )
        )
        await session.commit()

    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)

    task = await leases.claim("worker-1", lease_seconds=30)

    assert task is None, "claim() must not hand out work for a cancelled job"
    await engine.dispose()


async def test_runner_skips_provider_work_and_does_not_complete_a_cancelled_job() -> None:
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

    # Cancel lands after the claim but before the worker starts running the
    # task — the realistic race: a cancel request and an in-flight claim
    # interleave.
    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        job.status = "cancelling"
        job.cancel_requested = True
        await session.commit()

    processor = _Processor()
    runner = V2PageTaskRunner(sessions, store, processor, leases)
    await runner.run(task, owner="worker-1")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == "cancelled", "the last outstanding task must finalize the job"
        assert processor.calls == 0, "OpenAI/provider work must be skipped, not just the final status"
    await engine.dispose()


async def test_assembly_is_blocked_even_if_every_page_finished_in_flight() -> None:
    """Edge case: every page was already claimed and completed before
    cancel_requested was set (none hit the cancelled-skip path in run()).
    Assembly is still new work (extraction calls, PDF annotation) and must
    not run once cancellation was requested — it finalizes to CANCELLED
    instead of COMPLETED.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    store = _Store()
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.png",
                source_path="jobs-v2/job/source.png",
                source_mime="image/png",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status="processing",
                settings={"mode": "balanced", "segment_documents": True},
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()

    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)
    task = await leases.claim("worker-1", lease_seconds=30)
    assert task is not None

    # Simulate "this page finished before cancel landed": mark it completed
    # directly via the leases API, bypassing run() entirely.
    await leases.complete(task.id, "worker-1", result_path="jobs-v2/job/pages/p0001.json")

    # Now cancel arrives, after the only page already completed.
    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        job.cancel_requested = True
        await session.commit()

    runner = V2PageTaskRunner(sessions, store, _Processor(), leases)
    await runner._assemble_with_retries("job")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == "cancelled", "assembly must not run once cancellation was requested"
    await engine.dispose()


@pytest.mark.asyncio
async def test_cancel_endpoint_rejects_second_concurrent_request(client) -> None:
    from app.database import get_db
    from app.main import app
    from app.models.enums import JobStatus

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="race-cancel-job",
                original_filename="scan.png",
                source_path="jobs-v2/race-cancel-job/source.png",
                source_mime="image/png",
                source_size=1,
                source_sha256="b" * 64,
                page_count=1,
                status=JobStatus.QUEUED,
                settings={"api_family": "agentic_v2", "mode": "balanced"},
            )
        )
        await session.commit()

    async def _override_get_db():
        async with sessions() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = _override_get_db
    try:
        start = asyncio.Event()

        async def _cancel() -> int:
            await start.wait()
            response = await client.post("/v2/parse/jobs/race-cancel-job/cancel")
            return response.status_code

        first_task = asyncio.create_task(_cancel())
        second_task = asyncio.create_task(_cancel())
        start.set()
        first_status, second_status = await asyncio.gather(first_task, second_task)

        assert {first_status, second_status} == {200, 409}
        async with sessions() as session:
            job = await session.get(ParseJob, "race-cancel-job")
            assert job is not None and job.status == JobStatus.CANCELLED
    finally:
        if previous_override is not None:
            app.dependency_overrides[get_db] = previous_override
        else:
            app.dependency_overrides.pop(get_db, None)
        await engine.dispose()
