import asyncio
import datetime as dt

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db_models import Base, PageCheckpoint, ParseJob, V2PageTask
from app.services.v2_tasks import V2TaskLeases


async def test_page_tasks_are_claimed_once_and_expired_leases_are_recoverable() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs-v2/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=2,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
            )
        )
        await session.commit()

    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=2)

    first = await leases.claim("worker-a", lease_seconds=30)
    second = await leases.claim("worker-b", lease_seconds=30)
    none_left = await leases.claim("worker-c", lease_seconds=30)

    assert first is not None and first.page_number == 1
    assert second is not None and second.page_number == 2
    assert none_left is None

    async with sessions() as session:
        task = await session.get(V2PageTask, first.id)
        assert task is not None
        task.lease_expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
        await session.commit()

    reclaimed = await leases.claim("worker-c", lease_seconds=30)
    assert reclaimed is not None and reclaimed.id == first.id
    assert reclaimed.attempts == 2
    await engine.dispose()


async def test_completed_task_is_never_reclaimed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs-v2/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status="queued",
                settings={"mode": "economy", "segment_documents": False},
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=1)
    task = await leases.claim("worker", lease_seconds=30)
    assert task is not None

    await leases.complete(task.id, "worker", result_path="jobs-v2/job/pages/1.json")

    assert await leases.claim("other", lease_seconds=30) is None
    await engine.dispose()


async def test_terminal_tasks_recompute_job_summary_when_success_finishes_after_failure() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs-v2/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="c" * 64,
                page_count=2,
                status="processing",
                settings={"mode": "balanced", "segment_documents": True},
                pages=[
                    PageCheckpoint(page_number=1, status="pending"),
                    PageCheckpoint(page_number=2, status="pending"),
                ],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    await leases.enqueue_job("job", page_count=2)
    failed = await leases.claim("worker-a", lease_seconds=30)
    completed = await leases.claim("worker-b", lease_seconds=30)
    assert failed is not None and completed is not None

    await leases.fail(failed.id, "worker-a", error_message="ValidationError", max_attempts=1)

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        checkpoint = await session.get(PageCheckpoint, 1)
        assert job is not None and str(job.status) == "processing"
        assert job.completed_pages == 0 and job.failed_pages == 1
        assert checkpoint is not None and checkpoint.status == "failed" and checkpoint.attempts == 1

    await leases.complete(completed.id, "worker-b", result_path="jobs-v2/job/pages/p0002.json")

    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None and str(job.status) == "failed"
        assert job.completed_pages == 1 and job.failed_pages == 1
        assert job.error_code == "page_task_failed"
        assert job.error_message == "1 page task failed; first failed page: 1"
    await engine.dispose()


async def test_concurrent_terminal_transitions_finish_the_failed_job(tmp_path) -> None:
    # A file-backed database gives the two sessionmakers independent SQLite connections.
    # SQLite serializes writers database-wide; PostgreSQL uses the ParseJob row lock instead.
    database = (tmp_path / "task-race.sqlite").as_posix()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{database}",
        connect_args={"timeout": 5},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="race-job",
                original_filename="scan.pdf",
                source_path="jobs-v2/race-job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="d" * 64,
                page_count=2,
                status="processing",
                settings={"mode": "balanced", "segment_documents": True},
            )
        )
        await session.commit()
    first_leases = V2TaskLeases(sessions)
    second_leases = V2TaskLeases(sessions)
    await first_leases.enqueue_job("race-job", page_count=2)
    failed = await first_leases.claim("worker-a", lease_seconds=30)
    completed = await second_leases.claim("worker-b", lease_seconds=30)
    assert failed is not None and completed is not None

    start = asyncio.Event()

    async def fail_page() -> None:
        await start.wait()
        await first_leases.fail(
            failed.id, "worker-a", error_message="ValidationError", max_attempts=1
        )

    async def complete_page() -> None:
        await start.wait()
        await second_leases.complete(
            completed.id,
            "worker-b",
            result_path="jobs-v2/race-job/pages/p0002.json",
        )

    fail_transition = asyncio.create_task(fail_page())
    complete_transition = asyncio.create_task(complete_page())
    start.set()
    await asyncio.gather(fail_transition, complete_transition)

    async with sessions() as session:
        job = await session.get(ParseJob, "race-job")
        assert job is not None and str(job.status) == "failed"
        assert job.completed_pages == 1 and job.failed_pages == 1
    await engine.dispose()
