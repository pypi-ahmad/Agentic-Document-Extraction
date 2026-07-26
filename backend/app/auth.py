"""Optional shared-secret auth for exposing the API beyond localhost.

Disabled by default (empty API_KEY) to preserve the documented
single-operator, zero-config experience. Set API_KEY to require
X-API-Key on the routers that use this dependency.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(key: str | None = Security(_api_key_header)) -> None:
    if not settings.api_key:
        return
    if not key or not secrets.compare_digest(key, settings.api_key):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "Invalid or missing API key"},
        )
