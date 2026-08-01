from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.main import app
from app.rate_limit import FixedWindowLimiter, _identity, reset_rate_limiter_for_tests


@pytest.fixture
def rate_limited_settings() -> Iterator[None]:
    """Enable auth + rate limiting for the duration of one test, then restore."""
    original = (
        settings.testing,
        settings.api_key,
        settings.rate_limit_enabled,
        settings.rate_limit_requests_per_minute,
    )
    settings.testing = False
    settings.api_key = "test-secret-key"
    settings.rate_limit_enabled = True
    settings.rate_limit_requests_per_minute = 2
    reset_rate_limiter_for_tests()
    try:
        yield
    finally:
        (
            settings.testing,
            settings.api_key,
            settings.rate_limit_enabled,
            settings.rate_limit_requests_per_minute,
        ) = original
        reset_rate_limiter_for_tests()


@pytest_asyncio.fixture
async def rl_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


AUTH_HEADERS = {"X-API-Key": "test-secret-key"}


@pytest.mark.asyncio
async def test_enforcement_returns_429_after_limit_exceeded(rate_limited_settings, rl_client) -> None:
    first = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
    second = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
    third = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.asyncio
async def test_response_contract(rate_limited_settings, rl_client) -> None:
    await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
    await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
    response = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)

    assert response.status_code == 429
    body = response.json()
    assert body["detail"]["code"] == "rate_limited"
    assert "message" in body["detail"]
    assert int(response.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_auth_checked_before_rate_limit_and_bad_key_does_not_consume_budget(
    rate_limited_settings, rl_client
) -> None:
    bad = await rl_client.get(
        "/api/extraction-schemas", headers={"X-API-Key": "wrong-key"}
    )
    good_one = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
    good_two = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)

    assert bad.status_code == 401
    assert good_one.status_code == 200
    assert good_two.status_code == 200  # limit is 2 — both real attempts still fit


@pytest.mark.asyncio
async def test_rate_limit_disabled_flag_short_circuits(rate_limited_settings, rl_client) -> None:
    settings.rate_limit_enabled = False

    for _ in range(5):
        response = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_testing_flag_short_circuits(rate_limited_settings, rl_client) -> None:
    settings.testing = True

    for _ in range(5):
        response = await rl_client.get("/api/extraction-schemas", headers=AUTH_HEADERS)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_no_identity_when_auth_disabled_skips_limiting(rate_limited_settings, rl_client) -> None:
    settings.api_key = ""

    for _ in range(5):
        response = await rl_client.get("/api/extraction-schemas")
        assert response.status_code == 200


def test_identity_hash_is_stable_and_distinct_and_non_reversible() -> None:
    first = _identity("key-a")
    second = _identity("key-a")
    third = _identity("key-b")

    assert first == second
    assert first != third
    assert "key-a" not in first
    assert len(first) == 16


@pytest.mark.asyncio
async def test_fixed_window_limiter_allows_up_to_limit_then_blocks() -> None:
    limiter = FixedWindowLimiter(limit=2, window_seconds=60.0)

    assert await limiter.check("id", now=0) is None
    assert await limiter.check("id", now=0) is None
    retry_after = await limiter.check("id", now=0)

    assert retry_after is not None
    assert retry_after == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_fixed_window_limiter_resets_after_window_elapses() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60.0)

    assert await limiter.check("id", now=0) is None
    assert await limiter.check("id", now=30) is not None
    assert await limiter.check("id", now=61) is None


@pytest.mark.asyncio
async def test_fixed_window_limiter_isolates_identities() -> None:
    limiter = FixedWindowLimiter(limit=1, window_seconds=60.0)

    assert await limiter.check("id-a", now=0) is None
    assert await limiter.check("id-b", now=0) is None
    assert await limiter.check("id-a", now=0) is not None
