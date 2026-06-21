"""LLM provider registry and auto-selection policy."""

from __future__ import annotations

import logging
from dataclasses import replace

from app.config import settings
from app.models.enums import LLMProviderID, ModelCatalogSource, ProviderAvailabilityState
from app.services.llm.base import (
    BaseLLMProvider,
    LLMModelCatalog,
    LLMProviderStatus,
    ProviderAvailability,
    ProviderErrorInfo,
)

logger = logging.getLogger(__name__)

_PROVIDER_CLASSES: list[type[BaseLLMProvider]] = []
_PROVIDERS: dict[str, BaseLLMProvider] = {}

AUTO_PRIORITY = (
    LLMProviderID.OPENAI.value,
    LLMProviderID.GEMINI.value,
    LLMProviderID.ANTHROPIC.value,
)


def _import_builtin_providers() -> None:
    from app.services.llm.claude_provider import ClaudeProvider
    from app.services.llm.gemini_provider import GeminiProvider
    from app.services.llm.openai_provider import OpenAIProvider

    _PROVIDER_CLASSES.extend([OpenAIProvider, GeminiProvider, ClaudeProvider])


def _ensure_registered() -> None:
    if _PROVIDERS:
        return
    if not _PROVIDER_CLASSES:
        _import_builtin_providers()
    for cls in _PROVIDER_CLASSES:
        provider = cls()
        _PROVIDERS[provider.provider_id] = provider


def _iter_provider_ids_in_order() -> list[str]:
    ordered = [provider_id for provider_id in AUTO_PRIORITY if provider_id in _PROVIDERS]
    ordered.extend(provider_id for provider_id in _PROVIDERS if provider_id not in ordered)
    return ordered


def _default_provider_id() -> str:
    default_provider = settings.default_llm_provider
    return default_provider.value if hasattr(default_provider, "value") else str(default_provider)


def _decorate_status(provider: BaseLLMProvider) -> LLMProviderStatus:
    status = provider.get_status()
    return replace(status, is_default=provider.provider_id == _default_provider_id())


def get_llm_provider(provider_id: str) -> BaseLLMProvider:
    """Return a provider by ID.

    ``auto`` uses the configured default provider when it is ready, else
    falls back to the first ready provider in priority order.
    """

    _ensure_registered()
    if provider_id == LLMProviderID.AUTO.value:
        return _resolve_auto()

    provider = _PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError(f"Unknown LLM provider: {provider_id}")
    return provider


def list_llm_providers() -> list[BaseLLMProvider]:
    """Return all registered providers."""

    _ensure_registered()
    return list(_PROVIDERS.values())


def list_llm_provider_statuses() -> list[LLMProviderStatus]:
    """Return structured provider statuses in stable UI order."""

    _ensure_registered()
    return [
        _decorate_status(_PROVIDERS[provider_id]) for provider_id in _iter_provider_ids_in_order()
    ]


async def list_models_for_provider(provider_id: str) -> LLMModelCatalog:
    """Return the model list payload for a provider or for auto resolution."""

    _ensure_registered()

    if provider_id == LLMProviderID.AUTO.value:
        try:
            provider = _resolve_auto()
        except ValueError as exc:
            error = ProviderErrorInfo(
                code="no_provider_configured",
                message=str(exc),
            )
            return LLMModelCatalog(
                provider_id=LLMProviderID.AUTO.value,
                display_name="Auto",
                availability=ProviderAvailability(
                    state=ProviderAvailabilityState.ERROR,
                    configured=False,
                    available=False,
                    can_extract=False,
                    can_list_models=False,
                    auto_eligible=False,
                ),
                source=ModelCatalogSource.PLACEHOLDER,
                error=error,
            )

        catalog = await provider.list_models()
        return replace(
            catalog,
            provider_id=LLMProviderID.AUTO.value,
            display_name="Auto",
            resolved_provider_id=provider.provider_id,
        )

    provider = _PROVIDERS.get(provider_id)
    if provider is None:
        raise ValueError(f"Unknown LLM provider: {provider_id}")
    return await provider.list_models()


def register_provider(cls: type[BaseLLMProvider]) -> None:
    """Register an additional provider class at runtime."""

    _ensure_registered()
    if cls not in _PROVIDER_CLASSES:
        _PROVIDER_CLASSES.append(cls)
    provider = cls()
    _PROVIDERS[provider.provider_id] = provider


def reset_registry() -> None:
    """Clear and rebuild the registry. Test-only."""

    _PROVIDERS.clear()
    _PROVIDER_CLASSES.clear()
    _import_builtin_providers()
    _ensure_registered()


def _resolve_auto() -> BaseLLMProvider:
    default_provider_id = _default_provider_id()
    if default_provider_id != LLMProviderID.AUTO.value:
        provider = _PROVIDERS.get(default_provider_id)
        if provider and provider.get_status().availability.auto_eligible:
            return provider
        logger.warning(
            "DEFAULT_LLM_PROVIDER=%s is not ready; falling back to auto priority order.",
            default_provider_id,
        )

    for provider_id in AUTO_PRIORITY:
        provider = _PROVIDERS.get(provider_id)
        if provider and provider.get_status().availability.auto_eligible:
            return provider

    raise ValueError(
        "No LLM provider is ready. Set at least one provider API key and install "
        "the required client packages."
    )
