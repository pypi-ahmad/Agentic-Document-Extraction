"""Fixed-window, per-identity request throttling.

Identity is derived from the authenticated API key (never the raw key
itself — see :func:`_identity`). This app has exactly one shared
``API_KEY`` (see ``app.auth``), not per-client keys, so every legitimate
caller currently shares one budget. That's a property of the current auth
model, not something this module can fix — documented here rather than
silently implied away.

No IP or forwarded-header dimension is used for the rate-limit key, by
design: there is nothing header-derived in the key, so a spoofed
``X-Forwarded-For`` cannot buy a fresh limit window.

Single-process in-memory state. This mirrors the rest of the app's
deployment assumption (``job_max_concurrent`` is hardcoded to 1) — if this
service ever runs as multiple replicas, this state needs to move to a
shared store (e.g. Redis) to stay correct.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

from fastapi import Depends, HTTPException, Request

from app.auth import require_api_key
from app.config import settings
from app.logging_setup import get_logger

logger = get_logger("app.rate_limit")


def _identity(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class FixedWindowLimiter:
    """Allow at most ``limit`` requests per identity per ``window_seconds``."""

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._counts: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()

    async def check(self, identity: str, *, now: float | None = None) -> float | None:
        """Return ``None`` if allowed, or seconds-until-reset if throttled."""
        current = now if now is not None else time.monotonic()
        async with self._lock:
            window_start, count = self._counts.get(identity, (current, 0))
            if current - window_start >= self.window_seconds:
                window_start, count = current, 0
            if count >= self.limit:
                return self.window_seconds - (current - window_start)
            self._counts[identity] = (window_start, count + 1)
            return None

    def reset(self) -> None:
        self._counts.clear()


_limiter = FixedWindowLimiter(limit=settings.rate_limit_requests_per_minute)


def reset_rate_limiter_for_tests() -> None:
    """Rebuild the module-level limiter from current settings (test-only)."""
    global _limiter
    _limiter = FixedWindowLimiter(limit=settings.rate_limit_requests_per_minute)


async def require_rate_limit(
    request: Request, identity: str | None = Depends(require_api_key)
) -> None:
    if not settings.rate_limit_enabled or settings.testing or identity is None:
        return
    hashed = _identity(identity)
    retry_after = await _limiter.check(hashed)
    if retry_after is None:
        return
    seconds = max(1, round(retry_after))
    logger.warning(
        "rate_limit.exceeded",
        identity=hashed,
        path=request.url.path,
        retry_after=seconds,
    )
    raise HTTPException(
        status_code=429,
        detail={"code": "rate_limited", "message": "Too many requests. Retry later."},
        headers={"Retry-After": str(seconds)},
    )
