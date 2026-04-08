"""Tests for provider listing endpoints."""

import pytest
from httpx import AsyncClient

from app.services.llm.base import LLMModel, LLMModelCatalog, ProviderAvailability
from app.models.enums import ModelCatalogSource, ProviderAvailabilityState


@pytest.mark.asyncio
async def test_list_ocr_providers(client: AsyncClient):
    resp = await client.get("/api/providers/ocr")
    assert resp.status_code == 200
    providers = resp.json()
    assert isinstance(providers, list)
    ids = [p["id"] for p in providers]
    assert "paddleocr" in ids


@pytest.mark.asyncio
async def test_list_llm_providers(client: AsyncClient):
    resp = await client.get("/api/providers/llm")
    assert resp.status_code == 200
    providers = resp.json()
    ids = [p["id"] for p in providers]
    assert "openai" in ids
    assert "gemini" in ids
    assert "anthropic" in ids
    assert all("availability" in provider for provider in providers)
    assert all(provider["availability"]["state"] == "missing_api_key" for provider in providers)


@pytest.mark.asyncio
async def test_get_llm_models(client: AsyncClient):
    resp = await client.get("/api/providers/llm/openai/models")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["provider_id"] == "openai"
    assert payload["source"] == "placeholder"
    assert payload["models"] == []
    assert payload["error"]["code"] == "missing_api_key"


@pytest.mark.asyncio
async def test_get_llm_models_dynamic_payload(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    from app.services.llm.registry import get_llm_provider

    provider = get_llm_provider("openai")

    async def fake_list_models() -> LLMModelCatalog:
        return LLMModelCatalog(
            provider_id="openai",
            display_name="OpenAI",
            availability=ProviderAvailability(
                state=ProviderAvailabilityState.READY,
                configured=True,
                available=True,
                can_extract=True,
                can_list_models=True,
                auto_eligible=True,
            ),
            source=ModelCatalogSource.DYNAMIC,
            models=[
                LLMModel(
                    id="gpt-4o-mini",
                    name="gpt-4o-mini",
                    provider="openai",
                    is_default=True,
                )
            ],
        )

    monkeypatch.setattr(provider, "list_models", fake_list_models)

    resp = await client.get("/api/providers/llm/openai/models")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["source"] == "dynamic"
    assert payload["models"][0]["id"] == "gpt-4o-mini"
    assert payload["models"][0]["is_default"] is True


@pytest.mark.asyncio
async def test_get_llm_models_unknown_provider(client: AsyncClient):
    resp = await client.get("/api/providers/llm/unknown/models")
    assert resp.status_code == 404


# ── Parser endpoint ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parsers_excludes_internal(client: AsyncClient):
    """The /parsers endpoint should exclude internal helpers like PyMuPDF."""
    resp = await client.get("/api/providers/parsers")
    assert resp.status_code == 200
    parsers = resp.json()
    ids = [p["id"] for p in parsers]
    assert "pymupdf" not in ids
    assert "paddleocr" in ids


@pytest.mark.asyncio
async def test_parsers_response_shape(client: AsyncClient):
    resp = await client.get("/api/providers/parsers")
    assert resp.status_code == 200
    for parser in resp.json():
        assert "id" in parser
        assert "name" in parser
        assert "enabled" in parser
        assert "available" in parser
