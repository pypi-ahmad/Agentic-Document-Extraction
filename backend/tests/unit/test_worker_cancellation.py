import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.db_models import Base, ParseJob
from app.models.enums import JobStatus
from app.services.parsing.worker import _publish_stage


@pytest.fixture
async def sessions() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_stage_checkpoint_terminalizes_requested_cancellation(sessions) -> None:
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
                status=JobStatus.CANCELLING,
                cancel_requested=True,
                settings={},
            )
        )
        await session.commit()

    cancelled = await _publish_stage(sessions, "job", "zone_processing")

    assert cancelled is True
    async with sessions() as session:
        job = await session.get(ParseJob, "job")
        assert job is not None
        assert job.status == JobStatus.CANCELLED
        assert job.completed_at is not None
