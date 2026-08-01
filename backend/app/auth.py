"""Optional shared-secret auth for exposing the API beyond localhost.

Disabled by default (empty API_KEY) to preserve the documented
single-operator, zero-config experience. Set API_KEY to require an
``Authorization: Bearer`` token or the legacy ``X-API-Key`` header.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer = HTTPBearer(auto_error=False)


async def require_api_key(
    key: str | None = Security(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(_bearer),
) -> str | None:
    """Validate the shared API key. Returns the validated key, or ``None``
    when auth is disabled (empty ``API_KEY``) — callers that need a stable
    per-caller identity (e.g. rate limiting) can depend on this value.
    """
    if not settings.api_key:
        return None
    supplied = bearer.credentials if bearer and bearer.scheme.lower() == "bearer" else key
    if not supplied or not secrets.compare_digest(supplied, settings.api_key):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Invalid or missing API key"},
        )
    return supplied
