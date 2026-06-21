"""Tests for LLM registry, statuses, and model listing abstraction."""

from __future__ import annotations

import pytest

from app.models.enums import LLMProviderID, ModelCatalogSource, ProviderAvailabilityState
from app.services.llm.base import (
    BaseLLMProvider,
    LLMModel,
    LLMProviderError,
    LLMProviderStatus,
    ProviderAvailability,
    ProviderErrorInfo,
)
from app.services.llm.registry import (
    get_llm_provider,
    list_llm_provider_statuses,
    list_llm_providers,
    list_models_for_provider,
)


def _status(
    provider: BaseLLMProvider,
    state: ProviderAvailabilityState,
    *,
    configured: bool,
    available: bool,
    can_extract: bool,
    can_list_models: bool,
    auto_eligible: bool,
    error: ProviderErrorInfo | None = None,
) -> LLMProviderStatus:
    return LLMProviderStatus(
        provider_id=provider.provider_id,
        display_name=provider.display_name,
        availability=ProviderAvailability(
            state=state,
            configured=configured,
            available=available,
            can_extract=can_extract,
            can_list_models=can_list_models,
            auto_eligible=auto_eligible,
        ),
        error=error,
    )


def test_list_providers():
    providers = list_llm_providers()
    assert len(providers) == 3
    assert all(isinstance(p, BaseLLMProvider) for p in providers)


def test_provider_statuses_default_to_missing_api_key():
    statuses = list_llm_provider_statuses()
    assert [status.provider_id for status in statuses] == ["openai", "gemini", "anthropic"]
    assert all(
        status.availability.state == ProviderAvailabilityState.MISSING_API_KEY
        for status in statuses
    )
    assert all(status.error and status.error.code == "missing_api_key" for status in statuses)


def test_get_openai():
    provider = get_llm_provider("openai")
    assert provider.provider_id == "openai"
    assert provider.display_name == "OpenAI"


def test_get_claude():
    provider = get_llm_provider("anthropic")
    assert provider.provider_id == "anthropic"
    assert provider.display_name == "Anthropic Claude"


def test_get_unknown_provider():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("nonexistent")


def test_auto_raises_when_none_configured():
    with pytest.raises(ValueError, match="No LLM provider is ready"):
        get_llm_provider("auto")


def test_auto_uses_default_provider_when_ready(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings
    from app.services.llm import registry

    openai = get_llm_provider("openai")
    gemini = get_llm_provider("gemini")

    monkeypatch.setattr(settings, "default_llm_provider", LLMProviderID.GEMINI)
    monkeypatch.setattr(
        openai,
        "get_status",
        lambda: _status(
            openai,
            ProviderAvailabilityState.MISSING_API_KEY,
            configured=False,
            available=False,
            can_extract=False,
            can_list_models=False,
            auto_eligible=False,
            error=ProviderErrorInfo(
                code="missing_api_key", message="OpenAI API key is not configured."
            ),
        ),
    )
    monkeypatch.setattr(
        gemini,
        "get_status",
        lambda: _status(
            gemini,
            ProviderAvailabilityState.READY,
            configured=True,
            available=True,
            can_extract=True,
            can_list_models=True,
            auto_eligible=True,
        ),
    )

    provider = registry.get_llm_provider("auto")
    assert provider.provider_id == "gemini"


def test_auto_falls_back_when_default_not_ready(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings
    from app.services.llm import registry

    openai = get_llm_provider("openai")
    gemini = get_llm_provider("gemini")
    anthropic = get_llm_provider("anthropic")

    monkeypatch.setattr(settings, "default_llm_provider", LLMProviderID.ANTHROPIC)
    monkeypatch.setattr(
        openai,
        "get_status",
        lambda: _status(
            openai,
            ProviderAvailabilityState.READY,
            configured=True,
            available=True,
            can_extract=True,
            can_list_models=True,
            auto_eligible=True,
        ),
    )
    monkeypatch.setattr(
        gemini,
        "get_status",
        lambda: _status(
            gemini,
            ProviderAvailabilityState.MISSING_API_KEY,
            configured=False,
            available=False,
            can_extract=False,
            can_list_models=False,
            auto_eligible=False,
            error=ProviderErrorInfo(
                code="missing_api_key", message="Gemini API key is not configured."
            ),
        ),
    )
    monkeypatch.setattr(
        anthropic,
        "get_status",
        lambda: _status(
            anthropic,
            ProviderAvailabilityState.CLIENT_NOT_INSTALLED,
            configured=True,
            available=False,
            can_extract=False,
            can_list_models=False,
            auto_eligible=False,
            error=ProviderErrorInfo(
                code="client_not_installed", message="langchain-anthropic is not installed."
            ),
        ),
    )

    provider = registry.get_llm_provider("auto")
    assert provider.provider_id == "openai"


@pytest.mark.asyncio
async def test_model_listing_missing_key_returns_placeholder():
    catalog = await list_models_for_provider("openai")

    assert catalog.source == ModelCatalogSource.PLACEHOLDER
    assert catalog.models == []
    assert catalog.error is not None
    assert catalog.error.code == "missing_api_key"
    assert catalog.availability.state == ProviderAvailabilityState.MISSING_API_KEY


@pytest.mark.asyncio
async def test_provider_list_models_uses_dynamic_result(monkeypatch: pytest.MonkeyPatch):
    provider = get_llm_provider("openai")

    monkeypatch.setattr(provider, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(provider, "is_extraction_client_available", lambda: True)
    monkeypatch.setattr(provider, "is_model_listing_client_available", lambda: True)

    async def fake_dynamic() -> list[LLMModel]:
        return [
            LLMModel(id="gpt-4o-mini", name="gpt-4o-mini", provider="openai", is_default=True),
            LLMModel(id="gpt-4o", name="gpt-4o", provider="openai"),
        ]

    monkeypatch.setattr(provider, "_list_models_dynamic", fake_dynamic)

    catalog = await provider.list_models()
    assert catalog.source == ModelCatalogSource.DYNAMIC
    assert [model.id for model in catalog.models] == ["gpt-4o-mini", "gpt-4o"]
    assert catalog.availability.state == ProviderAvailabilityState.READY


@pytest.mark.asyncio
async def test_provider_list_models_returns_invalid_key_state(monkeypatch: pytest.MonkeyPatch):
    provider = get_llm_provider("openai")

    monkeypatch.setattr(provider, "get_api_key", lambda: "bad-key")
    monkeypatch.setattr(provider, "is_extraction_client_available", lambda: True)
    monkeypatch.setattr(provider, "is_model_listing_client_available", lambda: True)

    async def fake_dynamic() -> list[LLMModel]:
        raise LLMProviderError(
            provider.provider_id,
            "OpenAI API key is invalid or does not have model-listing access.",
            code="invalid_api_key",
        )

    monkeypatch.setattr(provider, "_list_models_dynamic", fake_dynamic)

    catalog = await provider.list_models()
    assert catalog.source == ModelCatalogSource.PLACEHOLDER
    assert catalog.error is not None
    assert catalog.error.code == "invalid_api_key"
    assert catalog.availability.state == ProviderAvailabilityState.INVALID_API_KEY


@pytest.mark.asyncio
async def test_auto_model_listing_returns_resolved_provider(monkeypatch: pytest.MonkeyPatch):
    from app.config import settings

    provider = get_llm_provider("openai")
    monkeypatch.setattr(settings, "default_llm_provider", LLMProviderID.OPENAI)
    monkeypatch.setattr(
        provider,
        "get_status",
        lambda: _status(
            provider,
            ProviderAvailabilityState.READY,
            configured=True,
            available=True,
            can_extract=True,
            can_list_models=True,
            auto_eligible=True,
        ),
    )

    async def fake_dynamic() -> list[LLMModel]:
        return [LLMModel(id="gpt-4o-mini", name="gpt-4o-mini", provider="openai", is_default=True)]

    monkeypatch.setattr(provider, "get_api_key", lambda: "test-key")
    monkeypatch.setattr(provider, "is_extraction_client_available", lambda: True)
    monkeypatch.setattr(provider, "is_model_listing_client_available", lambda: True)
    monkeypatch.setattr(provider, "_list_models_dynamic", fake_dynamic)

    catalog = await list_models_for_provider("auto")
    assert catalog.provider_id == "auto"
    assert catalog.resolved_provider_id == "openai"
    assert catalog.source == ModelCatalogSource.DYNAMIC


def test_prompts_build():
    from app.services.llm.prompts import build_extraction_prompt

    fields = [
        {
            "name": "company",
            "field_type": "string",
            "required": True,
            "description": "Company name",
        },
    ]
    prompt = build_extraction_prompt("Some document text", fields)
    assert "company" in prompt
    assert "Some document text" in prompt
    assert "JSON" in prompt
