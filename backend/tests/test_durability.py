"""Tests for job durability: retry endpoint, startup recovery, timeout wrapper."""

from __future__ import annotations

import asyncio
import datetime
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.main import _recover_orphaned_jobs
from app.models.db_models import (
    Document,
    Extraction,
    ExtractionReview,
    ExtractionSchema,
    ExtractionStep,
)
from tests.conftest import _test_session_maker

# ── Helpers ──────────────────────────────────────────────────────────


async def _seed_extraction(*, status: str = "failed", error: str | None = "boom") -> str:
    """Create Document + Schema + Extraction; return extraction id."""
    async with _test_session_maker() as db:
        doc = Document(
            filename="test.pdf",
            original_filename="test.pdf",
            file_path="/tmp/test.pdf",
            file_type="pdf",
            file_size=1024,
        )
        schema = ExtractionSchema(
            name=f"Invoice-{uuid.uuid4().hex[:8]}",
            fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )
        db.add_all([doc, schema])
        await db.flush()

        ext = Extraction(
            document_id=doc.id,
            schema_id=schema.id,
            status=status,
            error=error,
            ocr_provider="pymupdf",
            llm_provider="openai",
            llm_model="gpt-4o-mini",
        )
        db.add(ext)
        await db.flush()
        eid = ext.id
        await db.commit()
    return eid


def _patch_async_session():
    """Patch async_session in both main and extractions routers to use the test DB."""
    return (
        patch("app.main.async_session", _test_session_maker),
        patch("app.routers.extractions.async_session", _test_session_maker),
    )


# ── Retry endpoint ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_resets_failed_job(client: AsyncClient) -> None:
    eid = await _seed_extraction(status="failed", error="Pipeline error: timeout")
    with patch("app.routers.extractions._run_extraction_job", new=AsyncMock()):
        resp = await client.post(f"/api/extractions/{eid}/retry")
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["error"] is None
    assert data["result"] is None


@pytest.mark.asyncio
async def test_retry_commits_reset_state_before_background_execution(client: AsyncClient) -> None:
    """Background retry sees the cleared queued row, not stale failed state."""
    eid = await _seed_extraction(status="failed", error="Pipeline error: timeout")

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.started_at = datetime.datetime.now(datetime.UTC)
        ext.completed_at = datetime.datetime.now(datetime.UTC)
        ext.error_category = "timeout"
        db.add(ExtractionStep(extraction_id=eid, name="parse", status="failed", error="boom"))
        await db.commit()

    async def _assert_committed(extraction_id: str) -> None:
        async with _test_session_maker() as db:
            ext = await db.get(Extraction, extraction_id)
            assert ext is not None
            assert ext.status == "queued"
            assert ext.error is None
            assert ext.error_category is None
            assert ext.started_at is None
            assert ext.completed_at is None
            assert ext.steps == []

    runner = AsyncMock(side_effect=_assert_committed)
    with patch("app.routers.extractions._run_extraction_job", new=runner):
        resp = await client.post(f"/api/extractions/{eid}/retry")

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["steps"] == []
    runner.assert_awaited_once_with(eid)


@pytest.mark.asyncio
async def test_retry_rejects_non_failed(client: AsyncClient) -> None:
    eid = await _seed_extraction(status="completed", error=None)

    # Fix status to completed directly
    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "completed"
        ext.error = None
        await db.commit()

    resp = await client.post(f"/api/extractions/{eid}/retry")
    assert resp.status_code == 409
    assert "Only failed" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_not_found(client: AsyncClient) -> None:
    resp = await client.post("/api/extractions/nonexistent-id/retry")
    assert resp.status_code == 404


# ── Startup recovery ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recover_orphaned_jobs() -> None:
    """Stuck jobs (queued, processing, ocr_complete, extracted) are marked failed."""
    ids: dict[str, str] = {}
    for s in ("queued", "processing", "ocr_complete", "extracted"):
        ids[s] = await _seed_extraction(status=s, error=None)

    # Also seed a 'completed' and a 'failed' that should NOT be touched
    completed_id = await _seed_extraction(status="completed", error=None)
    already_failed_id = await _seed_extraction(status="failed", error="original error")

    # Fix statuses directly (seed helper defaults to 'failed')
    async with _test_session_maker() as db:
        for s, eid in ids.items():
            ext = await db.get(Extraction, eid)
            ext.status = s
            ext.error = None
        comp = await db.get(Extraction, completed_id)
        comp.status = "completed"
        comp.error = None
        await db.commit()

    p1, p2 = _patch_async_session()
    with p1, p2:
        await _recover_orphaned_jobs()

    async with _test_session_maker() as db:
        for s, eid in ids.items():
            ext = await db.get(Extraction, eid)
            assert ext.status == "failed", f"Expected {s} -> failed, got {ext.status}"
            assert "Server restarted" in ext.error
            assert ext.completed_at is not None, f"Expected completed_at set for {s}"
            assert ext.error_category == "unknown", f"Expected error_category for {s}"

        comp = await db.get(Extraction, completed_id)
        assert comp.status == "completed"

        af = await db.get(Extraction, already_failed_id)
        assert af.status == "failed"
        assert af.error == "original error"  # not overwritten


@pytest.mark.asyncio
async def test_recover_orphaned_running_steps_finalizes_timing() -> None:
    """Startup recovery closes running steps with completed_at and duration."""
    eid = await _seed_extraction(status="processing", error=None)
    started_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=2)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "processing"
        ext.error = None
        db.add(
            ExtractionStep(
                extraction_id=eid,
                name="parse",
                status="running",
                started_at=started_at,
            )
        )
        await db.commit()

    p1, p2 = _patch_async_session()
    with p1, p2:
        await _recover_orphaned_jobs()

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        step = ext.steps[0]
        assert step.status == "failed"
        assert step.completed_at is not None
        assert step.duration_ms is not None
        assert step.duration_ms >= 0
        assert "Server restarted" in (step.error or "")


@pytest.mark.asyncio
async def test_recover_orphaned_jobs_backfills_skipped_steps() -> None:
    """Crash recovery should preserve completed work and mark downstream steps as skipped."""
    eid = await _seed_extraction(status="ocr_complete", error=None)
    started_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=3)
    failed_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "ocr_complete"
        ext.error = None
        ext.started_at = started_at
        db.add(
            ExtractionStep(
                extraction_id=eid,
                name="parse",
                status="completed",
                started_at=started_at,
                completed_at=failed_at,
                duration_ms=2000,
            )
        )
        db.add(
            ExtractionStep(
                extraction_id=eid,
                name="extract",
                status="running",
                started_at=failed_at,
            )
        )
        await db.commit()

    p1, p2 = _patch_async_session()
    with p1, p2:
        await _recover_orphaned_jobs()

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        step_map = {step.name: step.status for step in ext.steps}
        assert step_map == {
            "parse": "completed",
            "extract": "failed",
            "validate": "skipped",
            "reflect": "skipped",
            "await_review": "skipped",
            "finalize": "skipped",
        }


# ── Timeout wrapper ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_marks_job_failed() -> None:
    """A hanging pipeline is terminated and its row marked failed."""
    from app.routers.extractions import _run_extraction_job

    eid = await _seed_extraction(status="queued", error=None)

    # Fix status back to queued
    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "queued"
        ext.error = None
        await db.commit()

    async def _hang(_id: str) -> None:
        await asyncio.sleep(9999)

    p1, p2 = _patch_async_session()
    with (
        p1,
        p2,
        patch("app.routers.extractions._run_extraction_pipeline", new=_hang),
        patch("app.routers.extractions._JOB_TIMEOUT", 0.1),
    ):
        await _run_extraction_job(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        assert "timed out" in ext.error
        assert ext.completed_at is not None
        assert ext.error_category == "timeout"


@pytest.mark.asyncio
async def test_timeout_finalizes_running_step_metadata() -> None:
    """Timeout cleanup closes running steps with coherent timing metadata."""
    from app.routers.extractions import _run_extraction_job

    eid = await _seed_extraction(status="queued", error=None)
    started_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "queued"
        ext.error = None
        db.add(
            ExtractionStep(
                extraction_id=eid,
                name="parse",
                status="running",
                started_at=started_at,
            )
        )
        await db.commit()

    async def _hang(_id: str) -> None:
        await asyncio.sleep(9999)

    p1, p2 = _patch_async_session()
    with (
        p1,
        p2,
        patch("app.routers.extractions._run_extraction_pipeline", new=_hang),
        patch("app.routers.extractions._JOB_TIMEOUT", 0.1),
    ):
        await _run_extraction_job(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        step = ext.steps[0]
        assert step.status == "failed"
        assert step.completed_at is not None
        assert step.duration_ms is not None
        assert step.duration_ms >= 0
        assert "timed out" in (step.error or "")


@pytest.mark.asyncio
async def test_timeout_backfills_downstream_steps_as_skipped() -> None:
    """Timeout cleanup should leave a coherent terminal step sequence."""
    from app.routers.extractions import _run_extraction_job

    eid = await _seed_extraction(status="queued", error=None)
    started_at = datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "queued"
        ext.error = None
        db.add(
            ExtractionStep(
                extraction_id=eid,
                name="parse",
                status="running",
                started_at=started_at,
            )
        )
        await db.commit()

    async def _hang(_id: str) -> None:
        await asyncio.sleep(9999)

    p1, p2 = _patch_async_session()
    with (
        p1,
        p2,
        patch("app.routers.extractions._run_extraction_pipeline", new=_hang),
        patch("app.routers.extractions._JOB_TIMEOUT", 0.1),
    ):
        await _run_extraction_job(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        step_map = {step.name: step.status for step in ext.steps}
        assert step_map == {
            "parse": "failed",
            "extract": "skipped",
            "validate": "skipped",
            "reflect": "skipped",
            "await_review": "skipped",
            "finalize": "skipped",
        }


@pytest.mark.asyncio
async def test_unexpected_error_marks_job_failed() -> None:
    """An unexpected exception in the pipeline results in a failed row."""
    from app.routers.extractions import _run_extraction_job

    eid = await _seed_extraction(status="queued", error=None)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "queued"
        ext.error = None
        await db.commit()

    async def _explode(_id: str) -> None:
        raise RuntimeError("kaboom")

    p1, p2 = _patch_async_session()
    with p1, p2, patch("app.routers.extractions._run_extraction_pipeline", new=_explode):
        await _run_extraction_job(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        assert "unexpected error" in ext.error.lower()
        assert ext.completed_at is not None
        assert ext.error_category == "unknown"


@pytest.mark.asyncio
async def test_pipeline_crash_finalizes_current_step_metadata() -> None:
    """A crash inside the pipeline closes the in-flight step cleanly."""
    from app.routers.extractions import _run_extraction_pipeline

    eid = await _seed_extraction(status="queued", error=None)

    async def _broken_astream(*_args, **_kwargs):
        raise RuntimeError("kaboom")
        yield  # pragma: no cover

    with (
        patch("app.routers.extractions.async_session", _test_session_maker),
        patch("app.services.extraction.graph.extraction_graph.astream", new=_broken_astream),
    ):
        await _run_extraction_pipeline(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        parse_step = ext.steps[0]
        # v0.4.0 pipeline starts with triage; the test simulates a
        # crash inside the graph stream, so the first recorded step
        # is triage (the running one) — not parse.
        assert parse_step.name == "triage"
        assert parse_step.status == "failed"
        assert parse_step.completed_at is not None
        assert parse_step.duration_ms is not None
        assert parse_step.duration_ms >= 0
        assert parse_step.error == "Internal error"


@pytest.mark.asyncio
async def test_missing_schema_is_normalized_as_failed() -> None:
    """Deleted schema during execution still yields normalized failed metadata."""
    from app.routers.extractions import _run_extraction_pipeline

    eid = await _seed_extraction(status="queued", error=None)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.schema_id = "missing-schema"
        await db.commit()

    with patch("app.routers.extractions.async_session", _test_session_maker):
        await _run_extraction_pipeline(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        assert ext.error == "Schema not found"
        assert ext.completed_at is not None
        assert ext.error_category == "unknown"


@pytest.mark.asyncio
async def test_missing_document_is_normalized_as_failed() -> None:
    """Deleted document during execution still yields normalized failed metadata."""
    from app.routers.extractions import _run_extraction_pipeline

    eid = await _seed_extraction(status="queued", error=None)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.document_id = "missing-document"
        await db.commit()

    with patch("app.routers.extractions.async_session", _test_session_maker):
        await _run_extraction_pipeline(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        assert ext.error == "Document not found"
        assert ext.completed_at is not None
        assert ext.error_category == "unknown"


# ── Retry clears step records ────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_clears_steps(client: AsyncClient) -> None:
    """Retrying a failed extraction deletes its previous step records."""
    eid = await _seed_extraction(status="failed", error="boom")

    # Seed step records
    async with _test_session_maker() as db:
        db.add(ExtractionStep(extraction_id=eid, name="parse", status="completed", duration_ms=100))
        db.add(ExtractionStep(extraction_id=eid, name="extract", status="failed", error="boom"))
        await db.commit()

    with patch("app.routers.extractions._run_extraction_job", new=AsyncMock()):
        resp = await client.post(f"/api/extractions/{eid}/retry")
    assert resp.status_code == 202
    assert resp.json()["steps"] == []

    # Verify in DB
    async with _test_session_maker() as db:
        from sqlalchemy import select

        result = await db.execute(select(ExtractionStep).where(ExtractionStep.extraction_id == eid))
        assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_retry_clears_review_history(client: AsyncClient) -> None:
    """Retrying a reviewer-rejected extraction deletes stale review rows."""
    eid = await _seed_extraction(status="failed", error="Rejected by reviewer")

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.review_verdict = "rejected"
        ext.reviewed_at = datetime.datetime.now(datetime.UTC)
        db.add(
            ExtractionReview(
                extraction_id=eid,
                decision="rejected",
                notes="Wrong document",
            )
        )
        await db.commit()

    with patch("app.routers.extractions._run_extraction_job", new=AsyncMock()):
        resp = await client.post(f"/api/extractions/{eid}/retry")

    assert resp.status_code == 202
    assert resp.json()["reviews"] == []

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.review_verdict is None
        assert ext.reviewed_at is None
        assert ext.reviews == []


# ── started_at tracking ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_clears_started_at(client: AsyncClient) -> None:
    """Retrying a failed extraction resets started_at."""
    import datetime

    eid = await _seed_extraction(status="failed", error="boom")

    # Set started_at as if the job had begun
    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.started_at = datetime.datetime.now(datetime.UTC)
        await db.commit()

    with patch("app.routers.extractions._run_extraction_job", new=AsyncMock()):
        resp = await client.post(f"/api/extractions/{eid}/retry")
    assert resp.status_code == 202
    assert resp.json()["started_at"] is None


@pytest.mark.asyncio
async def test_extraction_response_includes_started_at(client: AsyncClient) -> None:
    """GET extraction response includes the started_at field."""
    eid = await _seed_extraction(status="completed", error=None)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        ext.status = "completed"
        ext.error = None
        await db.commit()

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    assert "started_at" in resp.json()
