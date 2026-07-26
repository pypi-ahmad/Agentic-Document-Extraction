import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_parse_jobs_are_open_when_api_key_is_unset(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.api_key", "")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v2/jobs")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_parse_jobs_require_matching_api_key_when_set(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.api_key", "secret")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        missing = await client.get("/api/v2/jobs")
        wrong = await client.get("/api/v2/jobs", headers={"X-API-Key": "nope"})
        correct = await client.get("/api/v2/jobs", headers={"X-API-Key": "secret"})

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert correct.status_code == 200


@pytest.mark.asyncio
async def test_health_and_info_stay_open_regardless_of_api_key(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.api_key", "secret")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/health")
        info = await client.get("/info")

    assert health.status_code == 200
    assert info.status_code == 200
