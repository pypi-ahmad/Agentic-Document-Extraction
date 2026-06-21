"""Classify extraction errors into reviewer-friendly categories.

Error categories help reviewers quickly understand whether a failure
is actionable (e.g. fix the document) or operational (e.g. retry later).

Categories
----------
- ``auth``: API key missing or invalid
- ``rate_limit``: Provider rate limit / quota exceeded
- ``timeout``: Pipeline or provider timed out
- ``parse_error``: LLM returned unparseable output
- ``provider_error``: Provider-side error (5xx, service unavailable)
- ``file_error``: Input file missing, corrupt, or unsupported
- ``validation``: Extraction succeeded but failed validation
- ``unknown``: Unclassified error
"""

from __future__ import annotations


def classify_error(error: str | None, status: str = "") -> str | None:
    """Return a short category tag for the given error message.

    Returns ``None`` when the extraction has no error or the status
    does not indicate a problem (e.g. ``completed``).
    """
    if not error:
        if status == "needs_review":
            return "validation"
        return None

    lower = error.lower()

    if any(k in lower for k in ("api key", "api_key", "missing_api_key", "not configured")):
        return "auth"

    if any(k in lower for k in ("rate limit", "rate_limit", "429", "quota")):
        return "rate_limit"

    if any(k in lower for k in ("timed out", "timeout", "deadline")):
        return "timeout"

    if any(
        k in lower
        for k in ("unparseable", "invalid_json", "could not extract a json", "json", "parse")
    ):
        return "parse_error"

    if any(k in lower for k in ("not found", "file not found", "does not exist")):
        return "file_error"

    if any(
        k in lower
        for k in (
            "server error",
            "5xx",
            "502",
            "503",
            "500",
            "service unavailable",
            "provider_api_error",
        )
    ):
        return "provider_error"

    return "unknown"
