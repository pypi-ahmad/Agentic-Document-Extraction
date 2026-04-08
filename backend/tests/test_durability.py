"""Tests for job durability: retry endpoint, startup recovery, timeout wrapper."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.main import _recover_orphaned_jobs
from app.models.db_models import Document, Extraction, ExtractionSchema, ExtractionStep
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

        comp = await db.get(Extraction, completed_id)
        assert comp.status == "completed"

        af = await db.get(Extraction, already_failed_id)
        assert af.status == "failed"
        assert af.error == "original error"  # not overwritten


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
    with p1, p2, \
         patch("app.routers.extractions._run_extraction_pipeline", new=_hang), \
         patch("app.routers.extractions._JOB_TIMEOUT", 0.1):
        await _run_extraction_job(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        assert "timed out" in ext.error


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
    with p1, p2, \
         patch("app.routers.extractions._run_extraction_pipeline", new=_explode):
        await _run_extraction_job(eid)

    async with _test_session_maker() as db:
        ext = await db.get(Extraction, eid)
        assert ext.status == "failed"
        assert "unexpected error" in ext.error.lower()


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
        result = await db.execute(
            select(ExtractionStep).where(ExtractionStep.extraction_id == eid)
        )
        assert result.scalars().all() == []


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
