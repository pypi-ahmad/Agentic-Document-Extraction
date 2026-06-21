"""Project-wide constants.

This module is the single source of truth for any string literal that
flows through multiple layers (DB columns, API JSON, logs, UI). The
StrEnum in `app.models.enums` covers type-checked wire-format values;
this module covers operational constants, limits, and string tags
that don't have a small fixed set of legal values.
"""

from __future__ import annotations

# ── Versioning ────────────────────────────────────────────────────────
# The canonical project version is set in pyproject.toml and mirrored in
# backend/app/main.py::app.version. Keep those three in sync — the
# scripts/release.py helper automates this for tagged releases.

API_V1_PREFIX: str = "/api"
DEFAULT_REQUEST_TIMEOUT_S: float = 30.0
LONG_POLL_INTERVAL_S: float = 1.0
MAX_CONCURRENT_JOBS: int = 8
JOB_TIMEOUT_S: int = 300

# ── Streaming ────────────────────────────────────────────────────────
SSE_TERMINAL_STATUSES: frozenset[str] = frozenset({"completed", "needs_review", "failed"})
SSE_MAX_ITERATIONS: int = 600  # 10 minutes at 1 s/poll
SSE_KEEPALIVE_S: float = 15.0

# ── Cache control ────────────────────────────────────────────────────
NO_STORE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Expires": "0",
}
CACHE_MAX_AGE_PRESETS_S: int = 3600  # 1 h
CACHE_MAX_AGE_CONFIG_S: int = 300  # 5 min

# ── Logging ──────────────────────────────────────────────────────────
# Field names used by structlog and the JSON log renderer.
LOG_FIELD_EVENT: str = "event"
LOG_FIELD_REQUEST_ID: str = "request_id"
LOG_FIELD_USER: str = "user"
LOG_FIELD_EXTRACTION_ID: str = "extraction_id"
LOG_FIELD_DOCUMENT_ID: str = "document_id"
LOG_FIELD_PROVIDER: str = "provider"
LOG_FIELD_DURATION_MS: str = "duration_ms"
LOG_FIELD_STEP: str = "step"

# ── Request IDs ──────────────────────────────────────────────────────
REQUEST_ID_HEADER: str = "X-Request-ID"
REQUEST_ID_CONTEXT_KEY: str = "request_id"
REQUEST_ID_MAX_LENGTH: int = 128

# ── Security ─────────────────────────────────────────────────────────
SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
RATE_LIMIT_DEFAULT: str = "60/minute"
RATE_LIMIT_UPLOAD: str = "20/minute"
RATE_LIMIT_EXTRACT: str = "30/minute"

# ── File uploads ─────────────────────────────────────────────────────
UPLOAD_SNIFF_BYTES: int = 4096  # how many bytes to inspect for MIME
ALLOWED_MAGIC_PDF: bytes = b"%PDF-"
ALLOWED_MAGIC_PNG: bytes = b"\x89PNG\r\n\x1a\n"
ALLOWED_MAGIC_JPEG: bytes = b"\xff\xd8\xff"
ALLOWED_MAGIC_TIFF_LE: bytes = b"II\x2a\x00"
ALLOWED_MAGIC_TIFF_BE: bytes = b"MM\x00\x2a"

# ── Audit log ────────────────────────────────────────────────────────
AUDIT_LOG_TABLE: str = "extraction_audit_log"
AUDIT_EVENT_STARTED: str = "extraction.started"
AUDIT_EVENT_OCR_COMPLETE: str = "extraction.ocr_complete"
AUDIT_EVENT_EXTRACTED: str = "extraction.extracted"
AUDIT_EVENT_COMPLETED: str = "extraction.completed"
AUDIT_EVENT_NEEDS_REVIEW: str = "extraction.needs_review"
AUDIT_EVENT_FAILED: str = "extraction.failed"
AUDIT_EVENT_REVIEW_SUBMITTED: str = "extraction.review_submitted"
AUDIT_EVENT_RETRIED: str = "extraction.retried"

# ── Network guard for local-only services ────────────────────────────
# When OLLAMA_ALLOW_PRIVATE_HOSTS is false (the default), the URL must
# resolve to one of these hosts. Anything else is rejected at startup.
LOCAL_ONLY_HOSTS: frozenset[str] = frozenset(
    {
        "localhost",
        "127.0.0.1",
        "::1",
        "0.0.0.0",  # bind-only
    }
)
