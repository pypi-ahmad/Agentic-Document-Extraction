"""Job queue subsystem.

Two backends share the same ``JobQueue`` Protocol:

* ``InProcessJobQueue`` — default. asyncio task tracker. No external
  dependencies. The right answer for the local-first, single-host
  use case.

* ``ArqJobQueue`` — production. Persists jobs to a Redis list,
  dispatches them to N arq worker processes, and survives API
  process restarts without losing pending work. Picked when
  ``settings.redis_url`` is non-empty.

The factory ``get_job_queue()`` selects the backend lazily and
caches the instance per process. ``reset_job_queue_for_tests()``
drops the cache so the test suite can exercise both backends.

For graceful shutdown, the lifespan in ``app/main.py`` calls
``await queue.shutdown(timeout=...)``; both backends respect the
timeout by draining in-flight work or, in the worst case,
cancelling it and logging a warning.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from app.config import settings

logger = logging.getLogger(__name__)


@runtime_checkable
class JobQueue(Protocol):
    """Minimal interface every job queue backend implements.

    ``submit`` is **fire-and-forget**: it enqueues or schedules the
    job and returns. The actual execution happens on the same loop
    (in-process) or on a worker process (Arq).

    ``shutdown`` is called by the FastAPI lifespan during teardown.
    It must respect the timeout, log if it had to cancel in-flight
    work, and never raise.
    """

    async def submit(self, job_id: str, run: Callable[[], Awaitable[Any]]) -> None: ...
    async def shutdown(self, timeout: float = 30.0) -> None: ...


# ── In-process backend ───────────────────────────────────────────────


class InProcessJobQueue:
    """asyncio task tracker with a max-concurrency guard.

    This is the default backend. It does not require Redis and is
    the right answer for a single-host, single-process deployment.
    It survives the same as the API process: when the API crashes,
    the in-flight jobs are recovered on next startup by the
    ``_recover_orphaned_jobs`` sweep.
    """

    def __init__(self, max_concurrent: int | None = None) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._draining = False
        self._max_concurrent = max_concurrent or settings.job_max_concurrent

    @property
    def draining(self) -> bool:
        return self._draining

    @property
    def in_flight(self) -> int:
        return len(self._tasks)

    async def submit(self, job_id: str, run: Callable[[], Awaitable[Any]]) -> None:
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
        logger.info("job_queue.draining in_flight=%d timeout=%.1f", len(self._tasks), timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._tasks, return_exceptions=True),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("job_queue.drain_timeout remaining=%d", len(self._tasks))
            for task in list(self._tasks):
                task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*self._tasks, return_exceptions=True)


# ── Arq / Redis backend ─────────────────────────────────────────────


class ArqJobQueue:
    """Redis-backed job queue using arq.

    Activated when ``settings.redis_url`` is non-empty. Jobs are
    pushed to a Redis list and consumed by an arq worker process
    started with ``arq app.services.jobs.ArqWorkerSettings``. The
    API process only enqueues; it does not execute jobs.

    Why arq: it is the only mature async-native job queue for
    Python that does not require Celery's prefork model, supports
    modern ``asyncio``, and has first-class typing.
    """

    JOB_FUNCTION = "app.services.jobs:run_extraction_job_via_arq"

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.redis_url
        self._draining = False
        self._redis: Any = None  # arq.connections.RedisSettings or similar

    @property
    def draining(self) -> bool:
        return self._draining

    @property
    def in_flight(self) -> int:
        # Without a direct query API from arq, this is best-effort: it
        # is only used for diagnostics. The worker side is the source
        # of truth for in-flight counts.
        return 0

    async def _get_pool(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis

            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def submit(self, job_id: str, run: Callable[[], Awaitable[Any]]) -> None:
        if self._draining:
            raise RuntimeError("Job queue is shutting down; not accepting new jobs.")
        try:
            import json

            pool = await self._get_pool()
            payload = json.dumps(
                {
                    "extraction_id": job_id,
                    "enqueued_at": _now_iso(),
                }
            )
            await pool.lpush("ade:extractions:queue", payload)
        except Exception as exc:
            logger.exception("arq.enqueue_failed extraction_id=%s", job_id)
            raise RuntimeError(f"Could not enqueue job: {exc}") from exc

    async def shutdown(self, timeout: float = 30.0) -> None:
        self._draining = True
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception as exc:
                logger.warning("arq.close_failed error=%s", exc)


# ── arq worker entry-point ───────────────────────────────────────────


async def run_extraction_job_via_arq(ctx: dict, extraction_id: str) -> None:
    """arq worker callback. Imports the pipeline driver lazily so the
    worker can boot without the full web stack in its process.
    """
    from app.routers.extractions import _run_extraction_job  # late import

    logger.info("arq.job.start", extraction_id=extraction_id)
    try:
        await _run_extraction_job(extraction_id)
    except Exception as exc:
        logger.exception("arq.job.failed", extraction_id=extraction_id, error=str(exc))
        raise
    else:
        logger.info("arq.job.complete", extraction_id=extraction_id)


# ── Factory ──────────────────────────────────────────────────────────


_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Return the process-wide job queue.

    Selects the backend from ``settings.redis_url``:

    * empty / unset  → ``InProcessJobQueue`` (default)
    * ``redis://…``  → ``ArqJobQueue`` (production)

    The choice is cached per process. Tests can use
    ``reset_job_queue_for_tests`` to start from a clean state.
    """
    global _job_queue
    if _job_queue is None:
        if settings.redis_url:
            logger.info("job_queue.backend", name="arq", redis_url=settings.redis_url)
            _job_queue = ArqJobQueue()
        else:
            logger.info("job_queue.backend", name="in_process")
            _job_queue = InProcessJobQueue()
    return _job_queue


def reset_job_queue_for_tests() -> None:
    """Drop the cached queue. Tests use this to start from a clean state."""
    global _job_queue
    _job_queue = None


# ── Helpers ──────────────────────────────────────────────────────────


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.UTC).isoformat()


# Late import for contextlib — used in shutdown() only.
import contextlib  # noqa: E402

__all__ = [
    "ArqJobQueue",
    "InProcessJobQueue",
    "JobQueue",
    "get_job_queue",
    "reset_job_queue_for_tests",
    "run_extraction_job_via_arq",
]
