import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.db_models import Base, PageCheckpoint, ParseJob, V2PageTask
from app.services.parsing.contracts import BoundingBox
from app.services.parsing.ingest import DocumentInputError
from app.services.v2_jobs import V2JobQueue
from app.services.v2_tasks import V2TaskLeases


class _Runner:
    def __init__(self, leases: V2TaskLeases) -> None:
        self.leases = leases
        self.completed = asyncio.Event()

    async def run(self, task: V2PageTask, *, owner: str) -> None:
        await self.leases.complete(task.id, owner, result_path=f"pages/{task.page_number}.json")
        self.completed.set()


class _FailingRunner:
    def __init__(self) -> None:
        self.failed = asyncio.Event()

    async def run(self, task: V2PageTask, *, owner: str) -> None:
        if task.attempts == 3:
            self.failed.set()
        raise RuntimeError("provider timeout")


class _InvalidDocumentRunner:
    def __init__(self) -> None:
        self.failed = asyncio.Event()

    async def run(self, task: V2PageTask, *, owner: str) -> None:
        self.failed.set()
        raise DocumentInputError("invalid_pdf", "document is corrupted")


class _ValidationFailureRunner:
    def __init__(self) -> None:
        self.failed = asyncio.Event()

    async def run(self, task: V2PageTask, *, owner: str) -> None:
        self.failed.set()
        BoundingBox.model_validate({"left": 2, "top": 0, "right": 1, "bottom": 1})


async def test_queue_enqueues_and_executes_durable_page_tasks() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="job",
                original_filename="scan.pdf",
                source_path="source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="a" * 64,
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    runner = _Runner(leases)
    queue = V2JobQueue(sessions, leases, runner, worker_count=1)
    await queue.start()

    await queue.submit("job")
    await asyncio.wait_for(runner.completed.wait(), timeout=2)
    await queue.shutdown()

    async with sessions() as session:
        rows = list(await session.scalars(select(V2PageTask)))
        assert len(rows) == 1 and rows[0].status == "completed"
    await engine.dispose()


async def test_queue_retries_then_marks_page_and_job_failed() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="failed-job",
                original_filename="scan.pdf",
                source_path="source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="b" * 64,
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    runner = _FailingRunner()
    queue = V2JobQueue(sessions, leases, runner, worker_count=1)
    await queue.start()

    await queue.submit("failed-job")
    await asyncio.wait_for(runner.failed.wait(), timeout=2)
    await asyncio.sleep(0.05)
    await queue.shutdown()

    async with sessions() as session:
        task = await session.scalar(select(V2PageTask))
        job = await session.get(ParseJob, "failed-job")
        assert task is not None and task.status == "failed" and task.attempts == 3
        assert job is not None and str(job.status) == "failed"
        assert job.error_code == "page_task_failed"
    await engine.dispose()


async def test_queue_fails_invalid_document_input_without_retrying() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="invalid-job",
                original_filename="scan.pdf",
                source_path="source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="c" * 64,
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    runner = _InvalidDocumentRunner()
    queue = V2JobQueue(sessions, leases, runner, worker_count=1)
    await queue.start()

    await queue.submit("invalid-job")
    await asyncio.wait_for(runner.failed.wait(), timeout=2)
    await asyncio.sleep(0.05)
    await queue.shutdown()

    async with sessions() as session:
        task = await session.scalar(select(V2PageTask))
        job = await session.get(ParseJob, "invalid-job")
        checkpoint = await session.scalar(select(PageCheckpoint))
        assert task is not None and task.status == "failed" and task.attempts == 1
        assert job is not None and str(job.status) == "failed"
        assert checkpoint is not None and checkpoint.status == "failed" and checkpoint.attempts == 1
        assert checkpoint.error_code == "DocumentInputError"
    await engine.dispose()


async def test_queue_fails_validation_error_without_retrying() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(
            ParseJob(
                id="validation-job",
                original_filename="scan.pdf",
                source_path="source.pdf",
                source_mime="application/pdf",
                source_size=1,
                source_sha256="d" * 64,
                page_count=1,
                status="queued",
                settings={"mode": "balanced", "segment_documents": True},
                pages=[PageCheckpoint(page_number=1, status="pending")],
            )
        )
        await session.commit()
    leases = V2TaskLeases(sessions)
    runner = _ValidationFailureRunner()
    queue = V2JobQueue(sessions, leases, runner, worker_count=1)
    await queue.start()

    await queue.submit("validation-job")
    await asyncio.wait_for(runner.failed.wait(), timeout=2)
    await asyncio.sleep(0.05)
    await queue.shutdown()

    async with sessions() as session:
        task = await session.scalar(select(V2PageTask))
        checkpoint = await session.scalar(select(PageCheckpoint))
        assert task is not None and task.status == "failed" and task.attempts == 1
        assert checkpoint is not None and checkpoint.error_code == "ValidationError"
    await engine.dispose()
