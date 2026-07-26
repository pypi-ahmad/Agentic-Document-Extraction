import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, ParseJob
from app.models.enums import JobStatus
from app.services.jobs import ParseJobQueue


def _job(job_id: str, *, status: JobStatus, cancel_requested: bool = False) -> ParseJob:
    return ParseJob(
        id=job_id,
        original_filename="scan.pdf",
        source_path=f"jobs/{job_id}/source.pdf",
        source_mime="application/pdf",
        source_size=1,
        source_sha256="a" * 64,
        page_count=1,
        status=status,
        cancel_requested=cancel_requested,
        settings={},
    )


@pytest.fixture
async def sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_in_flight_reflects_submitted_but_unfinished_jobs(monkeypatch, sessions) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def blocked(*args, **kwargs) -> None:
        started.set()
        await release.wait()

    monkeypatch.setattr("app.services.jobs.async_session", sessions)
    monkeypatch.setattr("app.services.jobs.run_parse_job", blocked)
    async with sessions() as session:
        session.add(_job("job", status=JobStatus.QUEUED))
        await session.commit()

    queue = ParseJobQueue()
    assert queue.in_flight == 0
    await queue.submit("job")
    await asyncio.wait_for(started.wait(), timeout=1)
    assert queue.in_flight == 1

    release.set()
    await queue.shutdown(timeout=1)
    assert queue.in_flight == 0


@pytest.mark.asyncio
async def test_job_timeout_pauses_job_like_a_shutdown(monkeypatch, sessions) -> None:
    monkeypatch.setattr("app.services.jobs.async_session", sessions)
    monkeypatch.setattr("app.services.jobs.settings.job_timeout_seconds", 0.05)

    async def hangs(*args, **kwargs) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            async with sessions() as session:
                job = await session.get(ParseJob, "job")
                job.status = JobStatus.PAUSED
                job.error_code = "server_shutdown"
                await session.commit()
            raise

    monkeypatch.setattr("app.services.jobs.run_parse_job", hangs)
    async with sessions() as session:
        session.add(_job("job", status=JobStatus.PROCESSING))
        await session.commit()

    queue = ParseJobQueue()
    await queue.submit("job")
    await asyncio.sleep(0.2)

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == JobStatus.PAUSED
    await queue.shutdown(timeout=1)


@pytest.mark.asyncio
async def test_shutdown_timeout_pauses_active_job_for_resume(monkeypatch, sessions) -> None:
    started = asyncio.Event()

    async def blocked(*args, **kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("app.services.jobs.async_session", sessions)
    monkeypatch.setattr("app.services.jobs.run_parse_job", blocked)
    async with sessions() as session:
        session.add(_job("job", status=JobStatus.PROCESSING))
        await session.commit()

    queue = ParseJobQueue()
    await queue.submit("job")
    await asyncio.wait_for(started.wait(), timeout=1)
    await queue.shutdown(timeout=0.01)

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == JobStatus.PAUSED
        assert job.cancel_requested is False
        assert job.error_code == "server_shutdown"


@pytest.mark.asyncio
async def test_shutdown_timeout_preserves_user_cancel_semantics(monkeypatch, sessions) -> None:
    started = asyncio.Event()

    async def blocked(*args, **kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("app.services.jobs.async_session", sessions)
    monkeypatch.setattr("app.services.jobs.run_parse_job", blocked)
    async with sessions() as session:
        session.add(_job("job", status=JobStatus.CANCELLING, cancel_requested=True))
        await session.commit()

    queue = ParseJobQueue()
    await queue.submit("job")
    await asyncio.wait_for(started.wait(), timeout=1)
    await queue.shutdown(timeout=0.01)

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == JobStatus.CANCELLED
        assert job.cancel_requested is True
        assert job.error_code is None


@pytest.mark.asyncio
async def test_shutdown_records_externally_cancelled_active_worker(monkeypatch, sessions) -> None:
    started = asyncio.Event()

    async def blocked(*args, **kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("app.services.jobs.async_session", sessions)
    monkeypatch.setattr("app.services.jobs.run_parse_job", blocked)
    async with sessions() as session:
        session.add(_job("job", status=JobStatus.PROCESSING))
        await session.commit()

    queue = ParseJobQueue()
    await queue.submit("job")
    await asyncio.wait_for(started.wait(), timeout=1)
    assert queue._consumer_task is not None
    queue._consumer_task.cancel()
    await queue.shutdown(timeout=1)

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None and job.status == JobStatus.PAUSED
        assert job.error_code == "server_shutdown"
