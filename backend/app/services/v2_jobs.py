"""Durable multi-worker queue for V2 page tasks."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from typing import Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.database import async_session
from app.models.db_models import ParseJob, V2PageTask
from app.services.parsing.openai_document import OpenAIDocumentAdapter
from app.services.parsing.storage import FileStore
from app.services.parsing.v2_pipeline import V2PageProcessor
from app.services.parsing.v2_schema_extraction import V2SchemaExtractor
from app.services.v2_tasks import V2TaskLeases
from app.services.v2_worker import V2PageTaskRunner


class TaskRunner(Protocol):
    async def run(self, task: V2PageTask, *, owner: str) -> None: ...


class V2JobQueue:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        leases: V2TaskLeases,
        runner: TaskRunner,
        *,
        worker_count: int,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.sessions = sessions
        self.leases = leases
        self.runner = runner
        self.worker_count = worker_count
        self.http = http
        self._wake = asyncio.Event()
        self._stopping = False
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        if self._workers:
            return
        self._stopping = False
        self._workers = [
            asyncio.create_task(self._consume(index), name=f"v2-page-worker-{index}")
            for index in range(self.worker_count)
        ]

    async def submit(self, job_id: str) -> None:
        async with self.sessions() as session:
            job = await session.get(ParseJob, job_id)
            if job is None:
                raise ValueError("job not found")
            page_count = job.page_count
        await self.leases.enqueue_job(job_id, page_count=page_count)
        self._wake.set()

    async def recover(self) -> None:
        self._wake.set()

    async def _consume(self, index: int) -> None:
        owner = f"{uuid.uuid4().hex}:{index}"
        while not self._stopping:
            await self._wake.wait()
            if self._stopping:
                return
            while not self._stopping:
                task = await self.leases.claim(owner, lease_seconds=300)
                if task is None:
                    break
                try:
                    await self.runner.run(task, owner=owner)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    with contextlib.suppress(RuntimeError):
                        await self.leases.fail(task.id, owner, error_message=type(exc).__name__)
            self._wake.clear()

    async def shutdown(self) -> None:
        self._stopping = True
        self._wake.set()
        for worker in self._workers:
            try:
                await asyncio.wait_for(worker, timeout=5)
            except TimeoutError:
                worker.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await worker
        self._workers.clear()
        if self.http is not None:
            await self.http.aclose()


_queue: V2JobQueue | None = None


def get_v2_job_queue() -> V2JobQueue:
    global _queue
    if _queue is None:
        http = httpx.AsyncClient(timeout=settings.openai_timeout_seconds)
        adapter = OpenAIDocumentAdapter(
            http, api_key=settings.openai_api_key, base_url=settings.openai_base_url
        )
        leases = V2TaskLeases(async_session)
        runner = V2PageTaskRunner(
            async_session,
            FileStore(settings.artifacts_path),
            V2PageProcessor(adapter),
            leases,
            extractor=V2SchemaExtractor(adapter),
        )
        _queue = V2JobQueue(
            async_session,
            leases,
            runner,
            worker_count=settings.v2_worker_count,
            http=http,
        )
    return _queue


def reset_v2_job_queue_for_tests() -> None:
    global _queue
    _queue = None
