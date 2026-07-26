import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, ParseJob
from app.models.enums import JobStatus
from app.routers.parse_jobs import parse_job_events


class _DisconnectStub:
    def __init__(self, disconnected: bool) -> None:
        self._disconnected = disconnected

    async def is_disconnected(self) -> bool:
        return self._disconnected


@pytest.fixture
async def sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


async def _job(sessions, *, status: JobStatus) -> None:
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="jobs/job/source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status=status,
                settings={},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_events_stop_immediately_when_client_already_disconnected(sessions) -> None:
    await _job(sessions, status=JobStatus.PROCESSING)

    async with sessions() as db:
        response = await parse_job_events(_DisconnectStub(True), "job", db)
        chunks = [chunk async for chunk in response.body_iterator]

    assert chunks == []


@pytest.mark.asyncio
async def test_events_yield_snapshot_and_close_on_terminal_status(sessions) -> None:
    await _job(sessions, status=JobStatus.COMPLETED)

    async with sessions() as db:
        response = await parse_job_events(_DisconnectStub(False), "job", db)
        chunks = [chunk async for chunk in response.body_iterator]

    assert len(chunks) == 1
    assert chunks[0].startswith("event: snapshot\ndata: ")
