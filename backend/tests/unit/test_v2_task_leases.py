import datetime as dt

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db_models import Base, ParseJob, V2PageTask
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
