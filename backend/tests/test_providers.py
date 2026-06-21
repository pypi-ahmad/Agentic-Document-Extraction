"""Tests for provider listing endpoints and provider adapter behavior."""

import builtins
import sys
from types import ModuleType, SimpleNamespace

import pytest
from httpx import AsyncClient

from app.config import settings
from app.models.enums import ModelCatalogSource, ProviderAvailabilityState
from app.services.extraction.graph import extract_node
from app.services.llm.base import LLMModel, LLMModelCatalog, LLMProviderError, ProviderAvailability
from app.services.llm.claude_provider import ClaudeProvider
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.openai_provider import OpenAIProvider

PROVIDER_CASES = [
    pytest.param(
        OpenAIProvider, "openai_api_key", "langchain_openai", "ChatOpenAI", "openai", id="openai"
    ),
    pytest.param(
        GeminiProvider,
        "gemini_api_key",
        "langchain_google_genai",
        "ChatGoogleGenerativeAI",
        "gemini",
        id="gemini",
    ),
    pytest.param(
        ClaudeProvider,
        "anthropic_api_key",
        "langchain_anthropic",
        "ChatAnthropic",
        "anthropic",
        id="anthropic",
    ),
]


def _install_fake_chat_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    class_name: str,
    chat_class: type,
) -> None:
    module = ModuleType(module_name)
    setattr(module, class_name, chat_class)
    monkeypatch.setitem(sys.modules, module_name, module)


def _state(**overrides):
    state = {
        "file_path": "sample.pdf",
        "schema_fields": [],
        "ocr_provider_id": "auto",
        "llm_provider_id": "auto",
        "llm_model_id": "auto",
        "status": "pending",
        "error": "",
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_list_ocr_providers(client: AsyncClient):
    resp = await client.get("/api/providers/ocr")
    assert resp.status_code == 200
    providers = resp.json()
    assert isinstance(providers, list)
    ids = [p["id"] for p in providers]
    assert "paddleocr" in ids
    assert "pymupdf" not in ids
    assert all("name" in provider for provider in providers)
    assert all("available" in provider for provider in providers)
    assert all("enabled" not in provider for provider in providers)


@pytest.mark.asyncio
async def test_list_ocr_providers_uses_legacy_ready_semantics(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    from app.routers import providers as providers_router

    monkeypatch.setattr(
        providers_router,
        "list_ocr_provider_statuses",
        lambda **kwargs: [
            SimpleNamespace(
                provider_id="paddleocr",
                display_name="PaddleOCR (local image OCR)",
                enabled=False,
                available=True,
            )
        ],
    )

    resp = await client.get("/api/providers/ocr")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "id": "paddleocr",
            "name": "PaddleOCR (local image OCR)",
            "available": False,
        }
    ]


@pytest.mark.asyncio
async def test_list_llm_providers(client: AsyncClient):
    resp = await client.get("/api/providers/llm")
    assert resp.status_code == 200
    providers = resp.json()
    names = {provider["id"]: provider["name"] for provider in providers}
    ids = [p["id"] for p in providers]
    assert "openai" in ids
    assert "gemini" in ids
    assert "anthropic" in ids
    assert names["anthropic"] == "Anthropic Claude"
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
    assert resp.json()["detail"] == "LLM provider not found"


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


@pytest.mark.parametrize(
    "provider_cls,key_attr,module_name,class_name,provider_id",
    PROVIDER_CASES,
)
@pytest.mark.asyncio
async def test_provider_extract_parses_and_coerces_consistently(
    monkeypatch: pytest.MonkeyPatch,
    provider_cls,
    key_attr: str,
    module_name: str,
    class_name: str,
    provider_id: str,
):
    monkeypatch.setattr(settings, key_attr, "test-key")
    captured: dict[str, str] = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured["kwargs"] = str(kwargs)

        async def ainvoke(self, prompt: str):
            captured["prompt"] = prompt
            return SimpleNamespace(
                content=(
                    '{"total": "1,234.56", "paid": "yes", '
                    '"date": "01/15/2024", "_confidence": '
                    '{"total": 0.25, "paid": 0.9, "date": 0.8}}'
                ),
                response_metadata={},
            )

    _install_fake_chat_module(monkeypatch, module_name, class_name, FakeChat)

    provider = provider_cls()
    result = await provider.extract(
        text="Invoice text",
        schema_fields=[
            {"name": "total", "field_type": "number", "required": True},
            {"name": "paid", "field_type": "boolean", "required": True},
            {"name": "date", "field_type": "date", "required": True},
        ],
    )

    assert '"_confidence" object' in captured["prompt"]
    assert result.provider == provider_id
    assert result.data == {
        "total": 1234.56,
        "paid": True,
        "date": "2024-01-15",
    }
    assert result.confidence == {"total": 0.25, "paid": 0.9, "date": 0.8}


@pytest.mark.parametrize(
    "provider_cls,key_attr,module_name,class_name,provider_id",
    PROVIDER_CASES,
)
@pytest.mark.asyncio
async def test_provider_extract_translates_transient_errors_to_retryable(
    monkeypatch: pytest.MonkeyPatch,
    provider_cls,
    key_attr: str,
    module_name: str,
    class_name: str,
    provider_id: str,
):
    monkeypatch.setattr(settings, key_attr, "test-key")

    class FakeChat:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, prompt: str):
            raise RuntimeError("429 rate limit exceeded")

    _install_fake_chat_module(monkeypatch, module_name, class_name, FakeChat)

    with pytest.raises(LLMProviderError) as exc_info:
        await provider_cls().extract(
            text="Invoice text",
            schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )

    assert exc_info.value.retryable is True


@pytest.mark.parametrize(
    "provider_cls,key_attr,module_name,class_name,provider_id",
    PROVIDER_CASES,
)
@pytest.mark.asyncio
async def test_provider_extract_sanitizes_raw_auth_errors(
    monkeypatch: pytest.MonkeyPatch,
    provider_cls,
    key_attr: str,
    module_name: str,
    class_name: str,
    provider_id: str,
):
    monkeypatch.setattr(settings, key_attr, "test-key")

    class FakeChat:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, prompt: str):
            raise RuntimeError("Authorization failed for api_key=secret-123")

    _install_fake_chat_module(monkeypatch, module_name, class_name, FakeChat)

    with pytest.raises(LLMProviderError) as exc_info:
        await provider_cls().extract(
            text="Invoice text",
            schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )

    assert exc_info.value.code == "invalid_api_key"
    assert "secret-123" not in exc_info.value.message
    assert "authentication failed" in exc_info.value.message.lower()


@pytest.mark.parametrize(
    "provider_cls,key_attr,module_name,class_name,provider_id",
    PROVIDER_CASES,
)
@pytest.mark.asyncio
async def test_extract_node_retries_with_real_provider_translation(
    monkeypatch: pytest.MonkeyPatch,
    provider_cls,
    key_attr: str,
    module_name: str,
    class_name: str,
    provider_id: str,
):
    monkeypatch.setattr(settings, key_attr, "test-key")
    call_count = 0

    class FakeChat:
        def __init__(self, **kwargs):
            pass

        async def ainvoke(self, prompt: str):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("429 rate limit exceeded")
            return SimpleNamespace(
                content='{"vendor": "Acme", "_confidence": {"vendor": 0.95}}',
                response_metadata={},
            )

    _install_fake_chat_module(monkeypatch, module_name, class_name, FakeChat)
    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: provider_cls(),
    )
    monkeypatch.setattr("app.services.extraction.graph._RETRY_BASE_DELAY", 0.0)

    result = await extract_node(
        _state(
            ocr_text="Invoice text",
            llm_provider_id=provider_id,
            schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )
    )

    assert result["status"] == "extracted"
    assert result["extract_attempts"] == 3
    assert result["llm_provider_used"] == provider_id
    assert result["confidence"] == {"vendor": 0.95}
    assert call_count == 3


@pytest.mark.parametrize(
    "provider_cls,key_attr,module_name,class_name,provider_id",
    PROVIDER_CASES,
)
@pytest.mark.asyncio
async def test_provider_extract_translates_import_time_failures_to_non_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
    provider_cls,
    key_attr: str,
    module_name: str,
    class_name: str,
    provider_id: str,
):
    monkeypatch.setattr(settings, key_attr, "test-key")
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == module_name:
            raise RuntimeError("broken native dependency")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(LLMProviderError) as exc_info:
        await provider_cls().extract(
            text="Invoice text",
            schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )

    assert exc_info.value.provider == provider_id
    assert exc_info.value.code == "client_not_installed"
    assert exc_info.value.retryable is False
    assert "unavailable in the current environment" in exc_info.value.message


@pytest.mark.parametrize(
    "provider_cls,key_attr,module_name,class_name,provider_id",
    PROVIDER_CASES,
)
@pytest.mark.asyncio
async def test_extract_node_fails_without_retry_when_provider_import_is_broken(
    monkeypatch: pytest.MonkeyPatch,
    provider_cls,
    key_attr: str,
    module_name: str,
    class_name: str,
    provider_id: str,
):
    monkeypatch.setattr(settings, key_attr, "test-key")
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == module_name:
            raise RuntimeError("broken native dependency")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: provider_cls(),
    )
    monkeypatch.setattr("app.services.extraction.graph._RETRY_BASE_DELAY", 0.0)

    result = await extract_node(
        _state(
            ocr_text="Invoice text",
            llm_provider_id=provider_id,
            schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )
    )

    assert result["status"] == "failed"
    assert result["extract_attempts"] == 1
    assert "unavailable in the current environment" in result["error"]
