"""Tests for SSE streaming endpoint and cache headers."""

import asyncio
import datetime
import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.db_models import Document, Extraction, ExtractionSchema, ExtractionStep
from tests.conftest import _test_session_maker

# ── SSE stream endpoint ─────────────────────────────────────────────

# The SSE generator uses ``async_session`` directly (not get_db DI).
# Patch it to the test session factory so the generator reads from
# the in-memory test database.
_SSE_SESSION_PATH = "app.routers.extractions.async_session"


async def _seed_extraction(
    *,
    status: str = "processing",
    result: dict | None = None,
    steps: list[dict] | None = None,
) -> str:
    async with _test_session_maker() as db:
        doc = Document(
            filename="test.pdf",
            original_filename="test.pdf",
            file_path="/tmp/test.pdf",
            file_type="application/pdf",
            file_size=100,
        )
        db.add(doc)
        await db.flush()

        schema = ExtractionSchema(
            name="Test Schema",
            fields=[{"name": "x", "field_type": "string", "required": True}],
        )
        db.add(schema)
        await db.flush()

        extraction = Extraction(
            document_id=doc.id,
            schema_id=schema.id,
            status=status,
            result=result,
        )
        db.add(extraction)
        await db.flush()

        if steps:
            for step in steps:
                db.add(ExtractionStep(extraction_id=extraction.id, **step))

        await db.commit()
        return extraction.id


@pytest.mark.asyncio
async def test_stream_not_found(client: AsyncClient):
    """SSE stream for non-existent extraction returns error event."""
    with patch(_SSE_SESSION_PATH, _test_session_maker):
        async with client.stream("GET", "/api/extractions/nonexistent/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            assert resp.headers.get("cache-control") == "no-store"
            assert resp.headers.get("pragma") == "no-cache"
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk
    data_line = body.decode().strip()
    assert data_line.startswith("data: ")
    payload = json.loads(data_line[6:])
    assert "error" in payload


@pytest.mark.asyncio
async def test_stream_terminal_extraction(client: AsyncClient):
    """SSE stream for a completed extraction emits one event and closes."""
    ext_id = await _seed_extraction(status="completed", result={"x": "hello"})

    with patch(_SSE_SESSION_PATH, _test_session_maker):
        async with client.stream("GET", f"/api/extractions/{ext_id}/stream") as resp:
            assert resp.status_code == 200
            assert resp.headers.get("cache-control") == "no-store"
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    events = [line[6:] for line in body.decode().strip().split("\n") if line.startswith("data: ")]
    assert len(events) == 1
    payload = json.loads(events[0])
    assert payload["status"] == "completed"
    assert payload["result"] == {"x": "hello"}


@pytest.mark.asyncio
async def test_stream_stops_after_max_iterations(client: AsyncClient):
    """SSE stream terminates after _SSE_MAX_ITERATIONS even if not terminal."""
    ext_id = await _seed_extraction(status="processing")

    with (
        patch(_SSE_SESSION_PATH, _test_session_maker),
        patch("app.routers.extractions._SSE_MAX_ITERATIONS", 3),
        patch("app.routers.extractions._SSE_POLL_INTERVAL", 0.01),
    ):
        async with client.stream("GET", f"/api/extractions/{ext_id}/stream") as resp:
            assert resp.status_code == 200
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    # Should have emitted exactly 1 event (first iteration detects change)
    # then stopped after 3 iterations total without hanging
    events = [line for line in body.decode().strip().split("\n") if line.startswith("data: ")]
    assert len(events) >= 1  # at least the initial status
    payload = json.loads(events[0][6:])
    assert payload["status"] == "processing"


@pytest.mark.asyncio
async def test_stream_emits_when_step_state_changes_without_count_change(client: AsyncClient):
    """Step status changes should emit even when extraction status and step count stay the same."""
    ext_id = await _seed_extraction(
        status="processing",
        steps=[{"name": "parse", "status": "running"}],
    )

    async def _complete_step() -> None:
        await asyncio.sleep(0.02)
        async with _test_session_maker() as db:
            extraction = await db.get(Extraction, ext_id)
            assert extraction is not None
            step = extraction.steps[0]
            step.status = "completed"
            step.completed_at = datetime.datetime.now(datetime.UTC)
            step.duration_ms = 25
            await db.commit()

    updater = asyncio.create_task(_complete_step())

    with (
        patch(_SSE_SESSION_PATH, _test_session_maker),
        patch("app.routers.extractions._SSE_MAX_ITERATIONS", 6),
        patch("app.routers.extractions._SSE_POLL_INTERVAL", 0.01),
    ):
        async with client.stream("GET", f"/api/extractions/{ext_id}/stream") as resp:
            assert resp.status_code == 200
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    await updater

    events = [
        json.loads(line[6:])
        for line in body.decode().strip().split("\n")
        if line.startswith("data: ")
    ]
    assert len(events) >= 2
    assert events[0]["status"] == "processing"
    assert events[0]["steps"][0]["status"] == "running"
    assert any(
        event["status"] == "processing" and event["steps"][0]["status"] == "completed"
        for event in events[1:]
    )


# ── Cache headers ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_presets_cache_header(client: AsyncClient):
    resp = await client.get("/api/schemas/presets")
    assert resp.status_code == 200
    assert "max-age=" in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_config_cache_header(client: AsyncClient):
    resp = await client.get("/api/providers/config")
    assert resp.status_code == 200
    assert "max-age=" in resp.headers.get("cache-control", "")


@pytest.mark.asyncio
async def test_dynamic_extraction_endpoints_disable_caching(client: AsyncClient):
    ext_id = await _seed_extraction(status="completed", result={"x": "hello"})

    for path in (
        "/api/extractions/",
        f"/api/extractions/{ext_id}",
        f"/api/extractions/{ext_id}/result",
        f"/api/extractions/{ext_id}/validation",
        f"/api/extractions/{ext_id}/steps",
        f"/api/extractions/{ext_id}/reviews",
    ):
        resp = await client.get(path)
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"
        assert resp.headers.get("pragma") == "no-cache"
        assert resp.headers.get("expires") == "0"


@pytest.mark.asyncio
async def test_runtime_metadata_endpoints_disable_caching(client: AsyncClient):
    for path in (
        "/api/providers/ocr",
        "/api/providers/parsers",
        "/api/providers/llm",
        "/api/providers/llm/openai/models",
        "/health",
        "/info",
    ):
        resp = await client.get(path)
        assert resp.status_code == 200
        assert resp.headers.get("cache-control") == "no-store"
        assert resp.headers.get("pragma") == "no-cache"
        assert resp.headers.get("expires") == "0"
