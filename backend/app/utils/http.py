"""HTTP helpers used across routers."""

from __future__ import annotations

from fastapi import Response

from app.constants import NO_STORE_HEADERS


def apply_no_store(response: Response) -> None:
    """Add the standard no-store headers to a response."""
    response.headers.update(NO_STORE_HEADERS)


def apply_cache(response: Response, max_age: int) -> None:
    """Set a public, max-age cache header on a response."""
    response.headers["Cache-Control"] = f"public, max-age={max_age}"


def with_extra_headers(extra: dict[str, str]) -> dict[str, str]:
    """Return a copy of NO_STORE_HEADERS merged with the given extras."""
    return {**NO_STORE_HEADERS, **extra}
