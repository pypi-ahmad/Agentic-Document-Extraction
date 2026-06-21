"""Shared test fixtures."""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override settings BEFORE importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["UPLOAD_DIR"] = str(Path(__file__).parent / "_test_uploads")
os.environ["OPENAI_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["TESTING"] = "1"  # disable the in-process rate limiter

from app.database import get_db
from app.main import app
from app.models.db_models import Base

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
_test_session_maker = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)


async def _override_get_db() -> AsyncIterator[AsyncSession]:
    async with _test_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


app.dependency_overrides[get_db] = _override_get_db


class _SyncJobQueue:
    """In-process test queue: runs the job to completion before returning.

    This preserves the synchronous semantics that the test suite
    relied on under FastAPI's BackgroundTasks — the test sends a
    POST, the job runs inside the request, and by the time the test
    asserts, the row is in its final state.
    """

    def __init__(self) -> None:
        self._draining = False
        self._inflight: set[Awaitable[Any]] = set()

    @property
    def draining(self) -> bool:
        return self._draining

    @property
    def in_flight(self) -> int:
        return len(self._inflight)

    async def submit(self, job_id: str, run: Callable[[], Awaitable[Any]]) -> None:
        if self._draining:
            raise RuntimeError("test queue is draining")
        # Run synchronously (await) so the test sees the final state.
        await run()

    async def shutdown(self, timeout: float = 5.0) -> None:
        self._draining = True


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables before each test and reset the in-process job queue."""
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Install the synchronous test queue for the duration of the test.
    from app.services.jobs import reset_job_queue_for_tests

    reset_job_queue_for_tests()
    from app.services import jobs as jobs_module

    jobs_module._job_queue = _SyncJobQueue()  # type: ignore[attr-defined]
    yield
    # Drain anything still in flight (none, in the sync queue, but
    # be defensive) and then drop the schema.
    jobs_module._job_queue = None  # type: ignore[attr-defined]
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
