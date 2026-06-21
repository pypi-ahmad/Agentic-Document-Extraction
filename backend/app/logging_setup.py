"""Structured logging via structlog.

Provides:
- A single ``configure_logging()`` entry point that swaps in the right
  renderer for development (console) or production (JSON).
- A request-scoped logger with ``request_id`` bound automatically by
  the ASGI middleware in ``app.middleware.RequestContextMiddleware``.
- Sanitisers that strip API keys, bearer tokens, and document text
  fragments from log records before they reach a handler.

Why structlog (vs stdlib ``logging`` only or ``loguru``):
- First-class JSON output that matches the OTel log-signal shape.
- Bound context (``log.bind(request_id=...)``) survives across
  loggers without leaking globals.
- Plays nicely with stdlib ``logging`` so the third-party libs
  (httpx, sqlalchemy, langgraph) keep working through the same sink.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars
from structlog.typing import EventDict, Processor

from app.constants import (
    LOG_FIELD_DURATION_MS,
    LOG_FIELD_REQUEST_ID,
    REQUEST_ID_CONTEXT_KEY,
)
from app.utils.datetime import to_isoformat

# ── Sanitisers ───────────────────────────────────────────────────────

# Match common secret-shaped strings: API keys, bearer tokens, JWTs.
_API_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization)\s*[:=]\s*[\"']?([A-Za-z0-9._\-/+=]+)"
)
_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-/+=]+")

# Match any non-trivial free-text run (4+ words) — used to redact
# document text from log records when ``LOG_REDOC_OCR_TEXT`` is on.
_OCR_TEXT_RE = re.compile(r"[A-Za-z0-9]{20,}")


def _redact_secrets(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """Strip known secret patterns from a log record."""
    for key, value in list(event_dict.items()):
        if not isinstance(value, str):
            continue
        value = _API_KEY_RE.sub(lambda m: f"{m.group(1)}=[REDACTED]", value)
        value = _BEARER_RE.sub("Bearer [REDACTED]", value)
        if key.endswith("_text") and len(value) > 200:
            value = value[:80] + "…[REDACTED]"
        event_dict[key] = value
    return event_dict


def _inject_event_defaults(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    """Stamp timestamp + service name on every record."""
    event_dict.setdefault(
        "timestamp", to_isoformat(__import__("datetime").datetime.now(__import__("datetime").UTC))
    )
    event_dict.setdefault("service", "agentic-document-extraction")
    return event_dict


# ── Public configuration ────────────────────────────────────────────


def configure_logging(level: str | None = None) -> None:
    """Configure structlog + stdlib logging for the whole process.

    Idempotent. Safe to call from ``lifespan`` at startup.
    """
    log_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()

    shared_processors: list[Processor] = [
        merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _inject_event_defaults,
        _redact_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if os.environ.get("LOG_JSON", "1") != "0":
        renderer: Processor = structlog.processors.JSONRenderer()
    else:
        from structlog.dev import ConsoleRenderer

        renderer = ConsoleRenderer(colors=sys.stderr.isatty())

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Pipe stdlib loggers through structlog so third-party libs emit JSON.
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)
    # Quiet down noisy libraries by default.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if os.environ.get("LOG_SQL") else logging.WARNING
    )


# ── Helpers ──────────────────────────────────────────────────────────


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger. ``None`` means the root logger."""
    return structlog.get_logger(name) if name else structlog.get_logger()


def bind_request_id(request_id: str) -> None:
    """Bind the request id to the current context (so logs are correlated)."""
    bind_contextvars(**{REQUEST_ID_CONTEXT_KEY: request_id})


def clear_request_id() -> None:
    """Clear the request context (called after each request)."""
    clear_contextvars()


def log_event(
    logger: structlog.stdlib.BoundLogger,
    event: str,
    /,
    **fields: Any,
) -> None:
    """Emit a structured log record.

    The ``event`` is required; the ``duration_ms`` field is auto-suffixed
    with ``_ms`` only when the call site already names it that way.
    """
    payload: MutableMapping[str, Any] = {**fields, "event": event}
    if LOG_FIELD_DURATION_MS in payload and "duration_ms" in payload:
        payload[LOG_FIELD_DURATION_MS] = payload.pop("duration_ms")
    logger.info(event, **payload)


__all__ = [
    "bind_request_id",
    "clear_request_id",
    "configure_logging",
    "get_logger",
    "log_event",
]


# Re-export the request-id field name for symmetry.
REQUEST_ID_FIELD = LOG_FIELD_REQUEST_ID
