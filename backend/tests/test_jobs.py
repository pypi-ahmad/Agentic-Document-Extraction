"""Tests for the job-queue backends."""

from __future__ import annotations

import asyncio
import contextlib

import pytest

from app.services.jobs import (
    ArqJobQueue,
    InProcessJobQueue,
    get_job_queue,
    reset_job_queue_for_tests,
)

# ── InProcessJobQueue ───────────────────────────────────────────────


async def test_in_process_queue_runs_job() -> None:
    q = InProcessJobQueue()
    ran: list[str] = []

    async def job() -> None:
        ran.append("x")

    submit_task = asyncio.create_task(q.submit("id-1", job))
    await submit_task
    # Give the scheduled task a chance to run.
    for _ in range(50):
        if ran:
            break
        await asyncio.sleep(0.01)
    assert ran == ["x"]


async def test_in_process_queue_in_flight_count() -> None:
    q = InProcessJobQueue()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> None:
        started.set()
        await release.wait()

    submit_task = asyncio.create_task(q.submit("id-2", slow))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    assert q.in_flight == 1
    release.set()
    await submit_task
    # The done-callback that removes the task from the set runs in a
    # follow-up loop tick; yield to it.
    for _ in range(50):
        if q.in_flight == 0:
            break
        await asyncio.sleep(0.01)
    assert q.in_flight == 0


async def test_in_process_queue_rejects_after_drain() -> None:
    q = InProcessJobQueue()
    await q.shutdown(timeout=1.0)
    with pytest.raises(RuntimeError):
        await q.submit("id-3", _noop)


async def test_in_process_queue_respects_max_concurrent() -> None:
    q = InProcessJobQueue(max_concurrent=1)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> None:
        started.set()
        await release.wait()

    submit_task = asyncio.create_task(q.submit("id-4", slow))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    with pytest.raises(RuntimeError):
        await q.submit("id-5", _noop)
    release.set()
    await submit_task


async def test_in_process_queue_shutdown_cancels_in_flight() -> None:
    q = InProcessJobQueue()
    started = asyncio.Event()
    release = asyncio.Event()

    async def stuck() -> None:
        started.set()
        await release.wait()

    submit_task = asyncio.create_task(q.submit("id-6", stuck))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    await q.shutdown(timeout=0.05)
    with contextlib.suppress(asyncio.CancelledError):
        await submit_task
    assert submit_task.cancelled() or submit_task.done()


async def _noop() -> None:
    pass


# ── get_job_queue factory ────────────────────────────────────────────


def test_factory_returns_in_process_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.jobs.settings.redis_url", "")
    reset_job_queue_for_tests()
    q = get_job_queue()
    assert isinstance(q, InProcessJobQueue)
    reset_job_queue_for_tests()


def test_factory_returns_arq_when_redis_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.jobs.settings.redis_url", "redis://localhost:6379/0")
    reset_job_queue_for_tests()
    q = get_job_queue()
    assert isinstance(q, ArqJobQueue)
    reset_job_queue_for_tests()


def test_factory_caches_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.jobs.settings.redis_url", "")
    reset_job_queue_for_tests()
    q1 = get_job_queue()
    q2 = get_job_queue()
    assert q1 is q2
    reset_job_queue_for_tests()
