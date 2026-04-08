"""Tests for SSE streaming endpoint and cache headers."""

import json
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.models.db_models import Document, ExtractionSchema, Extraction
from tests.conftest import _test_session_maker


# ── SSE stream endpoint ─────────────────────────────────────────────

# The SSE generator uses ``async_session`` directly (not get_db DI).
# Patch it to the test session factory so the generator reads from
# the in-memory test database.
_SSE_SESSION_PATH = "app.routers.extractions.async_session"


@pytest.mark.asyncio
async def test_stream_not_found(client: AsyncClient):
    """SSE stream for non-existent extraction returns error event."""
    with patch(_SSE_SESSION_PATH, _test_session_maker):
        async with client.stream(
            "GET", "/api/extractions/nonexistent/stream"
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
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
            status="completed",
            result={"x": "hello"},
        )
        db.add(extraction)
        await db.commit()
        ext_id = extraction.id

    with patch(_SSE_SESSION_PATH, _test_session_maker):
        async with client.stream(
            "GET", f"/api/extractions/{ext_id}/stream"
        ) as resp:
            assert resp.status_code == 200
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    events = [
        line[6:]
        for line in body.decode().strip().split("\n")
        if line.startswith("data: ")
    ]
    assert len(events) == 1
    payload = json.loads(events[0])
    assert payload["status"] == "completed"
    assert payload["result"] == {"x": "hello"}


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
