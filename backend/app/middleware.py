"""ASGI middleware: request-id propagation and lightweight access log."""

from __future__ import annotations

import contextlib
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.constants import (
    LOG_FIELD_REQUEST_ID,
    REQUEST_ID_CONTEXT_KEY,
    REQUEST_ID_HEADER,
    REQUEST_ID_MAX_LENGTH,
)
from app.logging_setup import bind_request_id, clear_request_id, get_logger

_logger = get_logger("app.middleware")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a request id to the log context and emit one access-log record per request.

    The request id is read from the inbound ``X-Request-ID`` header if
    present (so a reverse proxy can stitch traces); otherwise a UUID4
    is generated. The id is echoed back on the response so the client
    can correlate.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        inbound = request.headers.get(REQUEST_ID_HEADER, "").strip()
        request_id = inbound[:REQUEST_ID_MAX_LENGTH] if inbound else uuid.uuid4().hex

        clear_request_id()
        bind_request_id(request_id)

        t0 = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            with contextlib.suppress(Exception):  # logging must never break a request
                _logger.info(
                    "http.request",
                    method=request.method,
                    path=request.url.path,
                    status_code=status_code,
                    duration_ms=elapsed_ms,
                    request_id=request_id,
                    **{LOG_FIELD_REQUEST_ID: request_id, REQUEST_ID_CONTEXT_KEY: request_id},
                )
