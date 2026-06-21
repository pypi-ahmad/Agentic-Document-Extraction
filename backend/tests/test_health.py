"""Tests for the /health endpoint (lite and detailed modes)."""

from types import SimpleNamespace

import pytest
from httpx import AsyncClient

# ── Lightweight (default) health check ───────────────────────────────


@pytest.mark.asyncio
async def test_health_returns_ok(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    # Default mode should NOT include db stats or disk stats
    assert "db" not in data
    assert "disk" not in data


# ── Detailed health check (?detail=true) ─────────────────────────────


@pytest.mark.asyncio
async def test_health_detail_includes_db_stats(client: AsyncClient):
    resp = await client.get("/health", params={"detail": "true"})
    data = resp.json()
    assert data["status"] == "ok"
    assert "db" in data
    db = data["db"]
    assert "documents" in db
    assert "extractions" in db
    assert "failed" in db
    assert "size_mb" in db
    assert isinstance(db["documents"], int)
    assert db["documents"] >= 0


@pytest.mark.asyncio
async def test_health_detail_includes_disk_stats(client: AsyncClient):
    resp = await client.get("/health", params={"detail": "true"})
    data = resp.json()
    assert "disk" in data
    disk = data["disk"]
    assert "uploads_mb" in disk
    assert "artifacts_mb" in disk
    assert isinstance(disk["uploads_mb"], (int, float))


@pytest.mark.asyncio
async def test_health_detail_db_counts_increase(client: AsyncClient):
    """Verify that inserting a document is reflected in detailed stats."""
    from app.models.db_models import Document
    from tests.conftest import _test_session_maker

    async with _test_session_maker() as db:
        db.add(
            Document(
                filename="healthcheck.pdf",
                original_filename="healthcheck.pdf",
                file_path="/tmp/healthcheck.pdf",
                file_type="pdf",
                file_size=512,
            )
        )
        await db.commit()

    resp = await client.get("/health", params={"detail": "true"})
    data = resp.json()
    assert data["db"]["documents"] >= 1


def test_log_provider_readiness_handles_ready_provider_statuses(monkeypatch: pytest.MonkeyPatch):
    from app.main import _log_provider_readiness
    from app.services.llm import registry as llm_registry
    from app.services.ocr import registry as ocr_registry

    llm_calls: list[tuple[str, str]] = []
    ocr_calls: list[tuple[str, str]] = []

    class FakeLogger:
        def info(self, message: str, arg: str) -> None:
            if message.startswith("LLM"):
                llm_calls.append((message, arg))
            else:
                ocr_calls.append((message, arg))

        def warning(self, message: str) -> None:
            raise AssertionError(f"unexpected warning: {message}")

    monkeypatch.setattr(
        llm_registry,
        "list_llm_provider_statuses",
        lambda: [SimpleNamespace(provider_id="openai", available=True)],
    )
    monkeypatch.setattr(
        ocr_registry,
        "list_ocr_provider_statuses",
        lambda: [SimpleNamespace(provider_id="paddleocr", available=True, enabled=True)],
    )

    _log_provider_readiness(FakeLogger())

    assert llm_calls == [("LLM providers ready: %s", "openai")]
    assert ocr_calls == [("OCR providers ready: %s", "paddleocr")]
