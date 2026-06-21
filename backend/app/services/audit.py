"""Audit-log service.

The audit log is an append-only history of every meaningful extraction
lifecycle event. It is used by:

- the operator UI ("what happened to job X?");
- post-mortem investigation when a job misbehaved;
- any future compliance requirement ("who approved this, when, and
  with what request id?").

Design rules
------------

1. **Append-only.** There is no public mutation API. Application bugs
   that try to update an audit row will be caught by the type checker
   (the service exposes only ``record_audit_event``).
2. **Bounded payload.** The ``payload`` JSON column is small by
   convention (status, error category, a small subset of fields). We
   never put OCR text or LLM output in here.
3. **Fire-and-forget.** A write failure must not fail the parent
   operation. Errors are logged at WARN and swallowed.
"""

from __future__ import annotations

import contextlib
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.logging_setup import get_logger
from app.models.db_models import ExtractionAuditLog

_logger = get_logger("app.audit")


async def record_audit_event(
    db: AsyncSession,
    *,
    extraction_id: str,
    event: str,
    request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Append one audit row. Never raises."""
    try:
        db.add(
            ExtractionAuditLog(
                extraction_id=extraction_id,
                event=event,
                request_id=request_id,
                payload=payload or None,
            )
        )
        await db.flush()
    except Exception as exc:
        with contextlib.suppress(Exception):
            _logger.warning(
                "audit.write_failed",
                extraction_id=extraction_id,
                event=event,
                error=str(exc),
            )
