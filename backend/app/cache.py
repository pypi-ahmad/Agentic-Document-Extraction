"""In-process TTL cache for small, frequently-read values.

Used to short-circuit the public ``/api/providers/*`` endpoints and
``/api/providers/config`` for the same client. The cache is
per-process (no shared state across replicas) and is bounded by
both a maximum number of entries and a per-entry TTL.

For a multi-replica deployment, swap this for a Redis-backed cache;
the public interface is intentionally tiny.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

T = TypeVar("T")


class TTLCache:
    """Async-aware, asyncio-safe, FIFO-bounded TTL cache.

    Each entry is ``(value, expires_at)``. Reads refresh the *position*
    only when the entry is touched, not its TTL. Eviction is lazy
    (on miss) plus a capacity-driven purge when ``max_entries`` is
    exceeded.
    """

    def __init__(self, *, max_entries: int = 1024) -> None:
        self._store: dict[str, tuple[Any, float]] = {}
        self._lock = asyncio.Lock()
        self._max_entries = max_entries

    async def get_or_set(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
        ttl_seconds: float,
    ) -> T:
        """Return the cached value, or call ``loader`` and cache its result."""
        now = time.monotonic()
        async with self._lock:
            entry = self._store.get(key)
            if entry is not None and entry[1] > now:
                return entry[0]  # type: ignore[return-value]
        # Load outside the lock to keep contention low.
        value = await loader()
        async with self._lock:
            if len(self._store) >= self._max_entries:
                # Evict the entry closest to expiry (FIFO approximation).
                victim_key = min(self._store, key=lambda k: self._store[k][1])
                self._store.pop(victim_key, None)
            self._store[key] = (value, now + ttl_seconds)
        return value

    def invalidate(self, key: str | None = None) -> None:
        """Drop a specific key (or everything if ``key`` is None)."""
        if key is None:
            self._store.clear()
        else:
            self._store.pop(key, None)


# ── Module-level caches for the public config endpoints ─────────────

config_cache = TTLCache(max_entries=64)
parsers_cache = TTLCache(max_entries=64)
llm_providers_cache = TTLCache(max_entries=64)


__all__ = ["TTLCache", "config_cache", "llm_providers_cache", "parsers_cache"]
