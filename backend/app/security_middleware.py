"""Security middleware: default security headers on every response.

These are the *minimum* headers every API should send. They are added
unconditionally; reverse-proxy-layer policies (CSP, frame-ancestors,
HSTS, etc.) can layer on top.
"""

from __future__ import annotations

import contextlib

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.constants import SECURITY_HEADERS


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the standard security headers to every response."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        with contextlib.suppress(Exception):
            for header, value in SECURITY_HEADERS.items():
                response.headers.setdefault(header, value)
        return response
