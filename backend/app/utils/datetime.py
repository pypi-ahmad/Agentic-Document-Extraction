"""Datetime helpers used across the API and pipeline drivers."""

from __future__ import annotations

import datetime as _dt
from collections.abc import Mapping
from typing import Any


def ensure_utc(dt: _dt.datetime) -> _dt.datetime:
    """Treat naive datetimes as UTC; convert aware datetimes to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_dt.UTC)
    return dt.astimezone(_dt.UTC)


def duration_ms(start: _dt.datetime, end: _dt.datetime) -> int:
    """Non-negative wall-clock duration in milliseconds."""
    return max(int((ensure_utc(end) - ensure_utc(start)).total_seconds() * 1000), 0)


def utcnow_isoformat() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return _dt.datetime.now(_dt.UTC).isoformat()


def to_isoformat(dt: _dt.datetime | None) -> str | None:
    """Return the ISO-8601 string for ``dt``, or ``None`` when ``dt`` is None."""
    return None if dt is None else dt.isoformat()


def parse_isoformat(value: str | None) -> _dt.datetime | None:
    """Parse an ISO-8601 string into a datetime, or return ``None``."""
    if not value:
        return None
    return _dt.datetime.fromisoformat(value)


def safe_isoformat(value: Any) -> str | None:
    """Best-effort ISO-8601 formatter that never raises.

    Used by SSE / JSON encoders that may encounter a value from a legacy
    code path or third-party library.
    """
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return None
    return str(value)
