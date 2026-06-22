"""OCR provider registry and deterministic routing policy.

Design
------
* All concrete providers are registered once at import time.
* ``get_ocr_provider("auto", file_path=...)`` uses a deterministic,
    config-aware policy that walks a fixed priority list, checks
    feature-flags, runtime availability, and file-type support.
* Explicitly requesting an engine that is disabled, unavailable, or
    unsafe for the requested file type raises ``OCRProviderUnavailableError``.
* New engines only need to subclass ``BaseOCRProvider`` and be added to
    ``_PROVIDER_CLASSES``.

Parser contract
---------------
User-facing parsers are defined by the ``ParserEngine`` enum (``auto``,
``paddleocr``).  Internal helpers such as PyMuPDF are **not** members of
that enum and are **never** surfaced in ``/api/providers/parsers``.  They
are selected only by the Auto routing policy when the file type matches.
``list_ocr_provider_statuses(include_internal=False)`` enforces this
boundary; the router always uses the default ``False``.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.models.enums import ParserEngine
from app.services.ocr.base import (
    BaseOCRProvider,
    OCRProviderUnavailableError,
)
from app.utils.file_handler import get_file_type

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OCRProviderStatus:
    """Resolved status for an OCR provider as exposed to the UI."""

    provider_id: str
    display_name: str
    enabled: bool
    available: bool
    user_selectable: bool


# ── Provider class catalogue (append new engines here) ───────────────

_PROVIDER_CLASSES: list[type[BaseOCRProvider]] = []


def _import_builtin_providers() -> None:
    """Lazy-import to avoid circular deps and keep the catalogue tidy."""
    from app.services.ocr.docling_provider import DoclingProvider
    from app.services.ocr.glm_ocr_provider import GLMOCRProvider
    from app.services.ocr.paddleocr_provider import PaddleOCRProvider
    from app.services.ocr.pymupdf_provider import PyMuPDFProvider

    _PROVIDER_CLASSES.extend(
        [
            GLMOCRProvider,
            PaddleOCRProvider,
            DoclingProvider,
            PyMuPDFProvider,
        ]
    )


# ── Singleton registry ──────────────────────────────────────────────

_PROVIDERS: dict[str, BaseOCRProvider] = {}


def _ensure_registered() -> None:
    if _PROVIDERS:
        return
    if not _PROVIDER_CLASSES:
        _import_builtin_providers()
    for cls in _PROVIDER_CLASSES:
        inst = cls()
        _PROVIDERS[inst.provider_id] = inst


def _get_flag_name(provider: BaseOCRProvider) -> str | None:
    return provider.feature_flag_name


def _is_enabled(provider: BaseOCRProvider) -> bool:
    """Check whether the provider's feature flag is turned on."""

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
    ordered = [provider_id for provider_id in AUTO_PRIORITY if provider_id in _PROVIDERS]
    ordered.extend(provider_id for provider_id in _PROVIDERS if provider_id not in ordered)
    return ordered


# ── Auto routing policy ─────────────────────────────────────────────

# Priority order for Auto. First enabled + available + file-compatible engine wins.
AUTO_PRIORITY: Sequence[str] = (
    ParserEngine.GLMOCR.value,
    ParserEngine.PADDLEOCR.value,
    ParserEngine.DOCLING.value,
    "pymupdf",
)


def _resolve_auto(file_path: Path | None = None) -> BaseOCRProvider:
    """Deterministic Auto resolution.

    Walk ``AUTO_PRIORITY``. For each candidate:
    1. Is its feature flag enabled (or flag-exempt)?
    2. Is its runtime dependency available?
    3. Can it safely handle the requested file type?

    PyMuPDF is intentionally treated as a PDF-only parser. Auto will not
    silently use it for image uploads.
    """

    _ensure_registered()
    requested_file_type = _resolve_file_type(file_path)

    for pid in AUTO_PRIORITY:
        prov = _PROVIDERS.get(pid)
        if (
            prov
            and _is_enabled(prov)
            and prov.is_available()
            and prov.supports_file_type(requested_file_type)
        ):
            logger.debug("Auto-router selected %s", pid)
            return prov

    if requested_file_type and requested_file_type != "pdf":
        raise OCRProviderUnavailableError(
            ParserEngine.AUTO.value,
            "No enabled local OCR engine can safely process "
            f"'{requested_file_type}' files. Auto will not fall back to "
            "the PDF-only PyMuPDF parser.",
        )

    raise OCRProviderUnavailableError(
        ParserEngine.AUTO.value,
        "No enabled OCR/parser engine is currently available.",
    )


# ── Public API ──────────────────────────────────────────────────────


def get_ocr_provider(
    provider_id: str,
    *,
    file_path: Path | None = None,
) -> BaseOCRProvider:
    """Return a provider by ID.

    * ``"auto"`` — routes through ``_resolve_auto(file_path=...)``.
    * Explicit ID — returns that engine, or raises
      ``OCRProviderUnavailableError`` / ``ValueError``.
    """
    _ensure_registered()

    if provider_id == ParserEngine.AUTO.value:
        return _resolve_auto(file_path=file_path)

    provider = _PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError(f"Unknown OCR provider: '{provider_id}'. Registered: {sorted(_PROVIDERS)}")

    if not _is_enabled(provider):
        flag_name = _get_flag_name(provider) or ""
        raise OCRProviderUnavailableError(
            provider_id,
            f"Engine '{provider_id}' is disabled by configuration. "
            f"Set {flag_name.upper()}=true in .env to enable it.",
        )

    if not provider.is_available():
        raise OCRProviderUnavailableError(
            provider_id,
            f"Engine '{provider_id}' is enabled but its runtime dependencies are not installed.",
        )

    requested_file_type = _resolve_file_type(file_path)
    if not provider.supports_file_type(requested_file_type):
        raise OCRProviderUnavailableError(
            provider_id,
            f"Engine '{provider_id}' does not safely support "
            f"'{requested_file_type}' files in the current local integration.",
        )

    return provider


def list_ocr_providers() -> list[BaseOCRProvider]:
    """Return all registered providers (regardless of flags/availability)."""
    _ensure_registered()
    return list(_PROVIDERS.values())


def list_ocr_provider_statuses(
    *,
    include_internal: bool = False,
) -> list[OCRProviderStatus]:
    """Return OCR provider statuses without duplicating registry logic elsewhere."""

    _ensure_registered()
    statuses: list[OCRProviderStatus] = []
    for provider_id in _iter_provider_ids_in_order():
        provider = _PROVIDERS[provider_id]
        if not include_internal and not provider.is_user_selectable:
            continue
        statuses.append(
            OCRProviderStatus(
                provider_id=provider.provider_id,
                display_name=provider.display_name,
                enabled=_is_enabled(provider),
                available=provider.is_available(),
                user_selectable=provider.is_user_selectable,
            )
        )
    return statuses


def register_provider(cls: type[BaseOCRProvider]) -> None:
    """Register an additional provider class at runtime.

    Useful for plugins or test doubles.
    """
    _ensure_registered()
    if cls not in _PROVIDER_CLASSES:
        _PROVIDER_CLASSES.append(cls)
    inst = cls()
    _PROVIDERS[inst.provider_id] = inst


def reset_registry() -> None:
    """Clear and re-initialise the registry.  Test-only."""
    _PROVIDERS.clear()
    _PROVIDER_CLASSES.clear()
    _import_builtin_providers()
    _ensure_registered()
