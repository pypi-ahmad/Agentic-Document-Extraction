"""Single-consumer durable queue for local document parse jobs."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.db_models import ParseJob
from app.models.enums import JobStatus
from app.services.parsing.runtime import ParserRuntime
from app.services.parsing.storage import FileStore, ObjectStore
from app.services.parsing.worker import run_parse_job

logger = logging.getLogger(__name__)


class ParseJobQueue:
    def __init__(
        self, store: ObjectStore | None = None, runtime: ParserRuntime | None = None
    ) -> None:
        self.store = store or FileStore(settings.artifacts_path)
        self.runtime = runtime
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._consumer_task: asyncio.Task[None] | None = None
        self._submitted: set[str] = set()
        self._active_job_id: str | None = None
        self._interrupted_job_id: str | None = None

    @property
    def in_flight(self) -> int:
        return len(self._submitted)

    async def start(self, runtime: ParserRuntime | None = None) -> None:
        if runtime is not None:
            self.runtime = runtime
        if self._consumer_task is None or self._consumer_task.done():
            self._consumer_task = asyncio.create_task(self._consume(), name="parse-job-worker")

    async def submit(self, job_id: str) -> None:
        await self.start()
        if job_id not in self._submitted:
            self._submitted.add(job_id)
            await self._queue.put(job_id)

    async def _consume(self) -> None:
        while True:
            job_id = await self._queue.get()
            if job_id is None:
                self._queue.task_done()
                return
            try:
                self._active_job_id = job_id
                await asyncio.wait_for(
                    run_parse_job(job_id, async_session, self.store, self.runtime),
                    timeout=settings.job_timeout_seconds,
                )
            except asyncio.CancelledError:
                self._interrupted_job_id = job_id
                raise
            except Exception:
                logger.exception("parse_job.failed", extra={"job_id": job_id})
            finally:
                self._active_job_id = None
                self._submitted.discard(job_id)
                self._queue.task_done()

    async def recover(self) -> None:
        active = {
            JobStatus.INSPECTING,
            JobStatus.PROCESSING,
            JobStatus.ASSEMBLING,
            JobStatus.CANCELLING,
        }
        async with async_session() as session:
            jobs = list(await session.scalars(select(ParseJob)))
            queued: list[str] = []
            for job in jobs:
                if job.status in active:
                    job.status = JobStatus.PAUSED
                    job.error_code = "server_restarted"
                    job.error_message = (
                        "Server restarted while this job was active; resume to continue."
                    )
                elif job.status == JobStatus.QUEUED:
                    queued.append(job.id)
            await session.commit()
        for job_id in queued:
            await self.submit(job_id)

    async def shutdown(self, timeout: float = 30.0) -> None:
        if self._consumer_task is None:
            return
        await self._queue.put(None)
        try:
            await asyncio.wait_for(self._consumer_task, timeout=timeout)
        except TimeoutError:
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
            await self._record_active_shutdown()
        except asyncio.CancelledError:
            caller_cancelled = bool(asyncio.current_task() and asyncio.current_task().cancelling())
            self._consumer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer_task
            await self._record_active_shutdown()
            if caller_cancelled:
                raise
        finally:
            self._consumer_task = None
            self._interrupted_job_id = None

    async def _record_active_shutdown(self) -> None:
        interrupted_job_id = self._active_job_id or self._interrupted_job_id
        if interrupted_job_id is not None:
            await self._record_shutdown_interruption(interrupted_job_id)

    async def _record_shutdown_interruption(self, job_id: str) -> None:
        """Distinguish process shutdown from an explicit user cancellation."""
        async with async_session() as session:
            job = await session.get(ParseJob, job_id)
            if job is None:
                return
            if job.status not in {
                JobStatus.INSPECTING,
                JobStatus.PROCESSING,
                JobStatus.ASSEMBLING,
                JobStatus.CANCELLING,
            }:
                return
            if job.cancel_requested:
                job.status = JobStatus.CANCELLED
                job.error_code = None
                job.error_message = None
            else:
                job.status = JobStatus.PAUSED
                job.error_code = "server_shutdown"
                job.error_message = (
                    "Server shut down while this job was active; resume to continue."
                )
            await session.commit()


_queue: ParseJobQueue | None = None


def get_job_queue() -> ParseJobQueue:
    global _queue
    if _queue is None:
        _queue = ParseJobQueue()
    return _queue


def reset_job_queue_for_tests() -> None:
    global _queue
    _queue = None
