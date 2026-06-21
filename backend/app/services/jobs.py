"""Job queue subsystem (in-process + Arq backends).

This module is the implementation surface for Phase 5 of the v0.3.0
modernization. The graceful-shutdown handler in
``backend/app/main.py::lifespan`` already imports ``get_job_queue``
and calls ``await queue.shutdown(timeout=...)`` during teardown.

Concrete behaviour is added in the next phase. For now the module
exposes a ``get_job_queue()`` factory that returns the in-process
queue by default and is a no-op on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class JobQueue(Protocol):
    """Minimal interface every job queue backend implements."""

    async def submit(self, job_id: str, run: Any) -> None: ...
    async def shutdown(self, timeout: float = 30.0) -> None: ...


class InProcessJobQueue:
    """Default backend: in-memory asyncio task tracker.

    Holds a set of running asyncio tasks so the lifespan can wait
    for them on shutdown. Behaviour matches the prior in-process
    BackgroundTasks semantics: jobs run on the same event loop as
    the API.
    """

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._draining = False
        self._max_concurrent = int(os.environ.get("JOB_MAX_CONCURRENT", "8"))

    async def submit(self, job_id: str, run: Any) -> None:
        if self._draining:
            raise RuntimeError("Job queue is shutting down; not accepting new jobs.")
        if len(self._tasks) >= self._max_concurrent:
            raise RuntimeError(f"Job queue is at capacity ({self._max_concurrent}); retry shortly.")
        task = asyncio.create_task(run(), name=f"extraction-{job_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self, timeout: float = 30.0) -> None:
        self._draining = True
        if not self._tasks:
            return
        logger.info("job_queue.draining", in_flight=len(self._tasks), timeout=timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("job_queue.drain_timeout", remaining=len(self._tasks))
            for task in list(self._tasks):
                task.cancel()


_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Return the process-wide job queue.

    Backed by ``InProcessJobQueue`` until Phase 5 wires an Arq
    implementation gated on ``settings.redis_url``.
    """
    global _job_queue
    if _job_queue is None:
        _job_queue = InProcessJobQueue()
    return _job_queue


def reset_job_queue_for_tests() -> None:
    """Drop the cached queue. Tests use this to start from a clean state."""
    global _job_queue
    _job_queue = None


__all__ = ["InProcessJobQueue", "JobQueue", "get_job_queue", "reset_job_queue_for_tests"]
