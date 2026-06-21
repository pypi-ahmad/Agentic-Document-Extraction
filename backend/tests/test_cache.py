"""Tests for the in-process TTL cache."""

from __future__ import annotations

import asyncio

from app.cache import TTLCache


async def test_set_then_get() -> None:
    cache: TTLCache = TTLCache()
    counter = {"n": 0}

    async def loader() -> int:
        counter["n"] += 1
        return 42

    assert await cache.get_or_set("k", loader, ttl_seconds=10.0) == 42
    # Second call must hit the cache; loader is not invoked.
    assert await cache.get_or_set("k", loader, ttl_seconds=10.0) == 42
    assert counter["n"] == 1


async def test_ttl_expiry() -> None:
    cache: TTLCache = TTLCache()
    counter = {"n": 0}

    async def loader() -> int:
        counter["n"] += 1
        return counter["n"]

    assert await cache.get_or_set("k", loader, ttl_seconds=0.05) == 1
    await asyncio.sleep(0.1)
    assert await cache.get_or_set("k", loader, ttl_seconds=0.05) == 2


async def test_eviction_at_capacity() -> None:
    cache: TTLCache = TTLCache(max_entries=2)

    async def loader(v: int) -> int:
        return v

    await cache.get_or_set("a", lambda: loader(1), ttl_seconds=10.0)
    await cache.get_or_set("b", lambda: loader(2), ttl_seconds=10.0)
    await cache.get_or_set("c", lambda: loader(3), ttl_seconds=10.0)
    # Three entries were attempted but only 2 should remain.
    assert len(cache._store) == 2


async def test_invalidate() -> None:
    cache: TTLCache = TTLCache()

    async def loader() -> int:
        return 99

    await cache.get_or_set("k", loader, ttl_seconds=10.0)
    assert len(cache._store) == 1
    cache.invalidate("k")
    assert len(cache._store) == 0
    cache.invalidate()  # no-op on empty


async def test_invalidate_all() -> None:
    cache: TTLCache = TTLCache()

    async def loader() -> int:
        return 1

    await cache.get_or_set("a", loader, ttl_seconds=10.0)
    await cache.get_or_set("b", loader, ttl_seconds=10.0)
    assert len(cache._store) == 2
    cache.invalidate()
    assert len(cache._store) == 0
