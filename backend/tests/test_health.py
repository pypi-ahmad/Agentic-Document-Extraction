"""Tests for the enhanced /health endpoint and startup diagnostics."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_health_includes_db_stats(client: AsyncClient):
    resp = await client.get("/health")
    data = resp.json()
    assert "db" in data
    db = data["db"]
    assert "documents" in db
    assert "extractions" in db
    assert "failed" in db
    assert "size_mb" in db
    assert isinstance(db["documents"], int)
    assert db["documents"] >= 0


@pytest.mark.asyncio
async def test_health_includes_disk_stats(client: AsyncClient):
    resp = await client.get("/health")
    data = resp.json()
    assert "disk" in data
    disk = data["disk"]
    assert "uploads_mb" in disk
    assert "artifacts_mb" in disk
    assert isinstance(disk["uploads_mb"], (int, float))


@pytest.mark.asyncio
async def test_health_db_counts_increase_with_data(client: AsyncClient):
    """Verify that inserting a document is reflected in health stats."""
    from app.models.db_models import Document
    from tests.conftest import _test_session_maker

    async with _test_session_maker() as db:
        db.add(Document(
            filename="healthcheck.pdf",
            original_filename="healthcheck.pdf",
            file_path="/tmp/healthcheck.pdf",
            file_type="pdf",
            file_size=512,
        ))
        await db.commit()

    resp = await client.get("/health")
    data = resp.json()
    assert data["db"]["documents"] >= 1
