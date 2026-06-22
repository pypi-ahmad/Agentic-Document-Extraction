"""Layout provider registry.

Layout parsers are *parallel* to OCR providers. They share the same
registry design (singleton catalogue, deterministic auto-routing,
feature-flag gating, file-type compatibility) but expose a richer
contract (``LayoutResult`` instead of ``OCRResult``).

For v0.5.0 we ship exactly one layout engine: **Docling** running
in layout mode (it is already a v0.4.0 OCR provider, so we add a
sibling class that returns bbox + regions + reading order).

Adding a layout engine:

1. Subclass ``BaseLayoutProvider`` in a new module.
2. Add the import to ``_import_builtin_layout_providers``.
3. Append the class to ``_PROVIDER_CLASSES``.

The graph and the layout-aware routers call
``get_layout_provider("auto", file_path=...)``; the policy below
walks ``LAYOUT_AUTO_PRIORITY`` in order.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.services.ocr.layout_base import (
    BaseLayoutProvider,
    LayoutProviderUnavailableError,
)
from app.utils.file_handler import get_file_type

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LayoutProviderStatus:
    """Resolved status for a layout provider as exposed to the UI."""

    provider_id: str
    display_name: str
    enabled: bool
    available: bool
    user_selectable: bool


# ── Provider class catalogue (append new engines here) ───────────────

_PROVIDER_CLASSES: list[type[BaseLayoutProvider]] = []


def _import_builtin_layout_providers() -> None:
    """Lazy-import to avoid circular deps and keep the catalogue tidy."""

    from app.services.ocr.docling_layout_provider import DoclingLayoutProvider

    _PROVIDER_CLASSES.append(DoclingLayoutProvider)


# ── Singleton registry ──────────────────────────────────────────────

_PROVIDERS: dict[str, BaseLayoutProvider] = {}


def _ensure_registered() -> None:
    if _PROVIDERS:
        return
    if not _PROVIDER_CLASSES:
        _import_builtin_layout_providers()
    for cls in _PROVIDER_CLASSES:
        inst = cls()
        _PROVIDERS[inst.provider_id] = inst


def _get_flag_name(provider: BaseLayoutProvider) -> str | None:
    return provider.feature_flag_name


def _is_enabled(provider: BaseLayoutProvider) -> bool:
    flag_attr = _get_flag_name(provider)
    if flag_attr is None:
        return True
    return bool(getattr(settings, flag_attr, False))


def _resolve_file_type(file_path: Path | None) -> str | None:
    if file_path is None:
        return None
    file_type = get_file_type(file_path.name)
    return None if file_type == "unknown" else file_type


def _iter_provider_ids_in_order() -> list[str]:
    ordered = [provider_id for provider_id in LAYOUT_AUTO_PRIORITY if provider_id in _PROVIDERS]
    ordered.extend(provider_id for provider_id in _PROVIDERS if provider_id not in ordered)
    return ordered


# ── Auto routing policy ─────────────────────────────────────────────

# Priority order for layout Auto. First enabled + available +
# file-compatible engine wins.
LAYOUT_AUTO_PRIORITY: Sequence[str] = ("docling-layout",)


def _resolve_auto(file_path: Path | None = None) -> BaseLayoutProvider:
    """Deterministic Auto resolution for layout providers."""

    _ensure_registered()
    requested_file_type = _resolve_file_type(file_path)

    for pid in LAYOUT_AUTO_PRIORITY:
        prov = _PROVIDERS.get(pid)
        if (
            prov
            and _is_enabled(prov)
            and prov.is_available()
            and prov.supports_file_type(requested_file_type)
        ):
            logger.debug("Layout Auto-router selected %s", pid)
            return prov

    raise LayoutProviderUnavailableError(
        "auto",
        "No enabled layout engine is currently available. "
        "Install and enable docling, or disable layout parsing.",
    )


# ── Public API ──────────────────────────────────────────────────────


def get_layout_provider(
    provider_id: str,
    *,
    file_path: Path | None = None,
) -> BaseLayoutProvider:
    """Return a layout provider by ID.

    * ``"auto"`` — routes through ``_resolve_auto(file_path=...)``.
    * Explicit ID — returns that engine, or raises.
    """
    _ensure_registered()

    if provider_id == "auto":
        return _resolve_auto(file_path=file_path)

    provider = _PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError(
            f"Unknown layout provider: '{provider_id}'. Registered: {sorted(_PROVIDERS)}"
        )

    if not _is_enabled(provider):
        flag_name = _get_flag_name(provider) or ""
        raise LayoutProviderUnavailableError(
            provider_id,
            f"Layout engine '{provider_id}' is disabled by configuration. "
            f"Set {flag_name.upper()}=true in .env to enable it.",
        )

    if not provider.is_available():
        raise LayoutProviderUnavailableError(
            provider_id,
            f"Layout engine '{provider_id}' is enabled but its runtime "
            "dependencies are not installed.",
        )

    requested_file_type = _resolve_file_type(file_path)
    if not provider.supports_file_type(requested_file_type):
        raise LayoutProviderUnavailableError(
            provider_id,
            f"Layout engine '{provider_id}' does not safely support "
            f"'{requested_file_type}' files in the current local integration.",
        )

    return provider


def list_layout_providers() -> list[BaseLayoutProvider]:
    """Return all registered layout providers (regardless of flags/availability)."""

    _ensure_registered()
    return list(_PROVIDERS.values())


def list_layout_provider_statuses() -> list[LayoutProviderStatus]:
    """Return layout provider statuses (user-selectable only)."""

    _ensure_registered()
    statuses: list[LayoutProviderStatus] = []
    for provider_id in _iter_provider_ids_in_order():
        provider = _PROVIDERS[provider_id]
        if not provider.is_user_selectable:
            continue
        statuses.append(
            LayoutProviderStatus(
                provider_id=provider.provider_id,
                display_name=provider.display_name,
                enabled=_is_enabled(provider),
                available=provider.is_available(),
                user_selectable=provider.is_user_selectable,
            )
        )
    return statuses


def register_layout_provider(cls: type[BaseLayoutProvider]) -> None:
    """Register an additional layout provider class at runtime."""

    _ensure_registered()
    if cls not in _PROVIDER_CLASSES:
        _PROVIDER_CLASSES.append(cls)
    inst = cls()
    _PROVIDERS[inst.provider_id] = inst


def reset_layout_registry() -> None:
    """Clear and re-initialise the layout registry. Test-only."""

    _PROVIDERS.clear()
    _PROVIDER_CLASSES.clear()
    _import_builtin_layout_providers()
    _ensure_registered()
