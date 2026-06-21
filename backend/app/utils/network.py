"""Network guard for local-only services (e.g. local Ollama).

By default, ``OLLAMA_BASE_URL`` must point at a loopback / localhost
host. Anything else is rejected at startup with a clear error. An
explicit ``OLLAMA_ALLOW_PRIVATE_HOSTS=true`` opt-out exists for
operators who deliberately want to talk to a remote service.
"""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from app.constants import LOCAL_ONLY_HOSTS


class UnsafeOllamaURLError(ValueError):
    """Raised when OLLAMA_BASE_URL points at a non-local host without explicit opt-in."""


def _is_loopback_host(host: str) -> bool:
    """Return True if the host resolves to a loopback or unspecified address.

    Handles the four common shapes:
    - a literal hostname (e.g. ``localhost``) — must be in the allowlist;
    - a literal IPv4/IPv6 address (e.g. ``127.0.0.1``, ``::1``) — must be loopback;
    - anything else is rejected.
    """
    if not host:
        return False
    if host.lower() in LOCAL_ONLY_HOSTS:
        return True
    with contextlib.suppress(ValueError):
        ip = ipaddress.ip_address(host)
        return ip.is_loopback or ip.is_link_local or ip.is_unspecified
    return False


def validate_ollama_base_url(url: str) -> None:
    """Raise if ``url`` is not safe to call by default.

    Rules:
    1. Must be a valid http/https URL.
    2. Must include a host.
    3. The host must be a loopback / local address, OR
       ``OLLAMA_ALLOW_PRIVATE_HOSTS=true`` must be set in the environment.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeOllamaURLError(
            f"OLLAMA_BASE_URL must use http or https; got scheme={parsed.scheme!r}."
        )
    if not parsed.hostname:
        raise UnsafeOllamaURLError("OLLAMA_BASE_URL must include a host.")

    if _is_loopback_host(parsed.hostname):
        return

    if os.environ.get("OLLAMA_ALLOW_PRIVATE_HOSTS", "").lower() in {"1", "true", "yes"}:
        return

    raise UnsafeOllamaURLError(
        f"OLLAMA_BASE_URL host {parsed.hostname!r} is not a loopback / local address. "
        "If you deliberately want to talk to a non-local Ollama, set "
        "OLLAMA_ALLOW_PRIVATE_HOSTS=true in the environment."
    )


# Late import for the contextlib used above — keeps module import cheap.
import contextlib  # noqa: E402
