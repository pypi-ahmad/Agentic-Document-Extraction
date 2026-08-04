import json

import httpx
import pytest

from app.config import Settings
from app.services.parsing.vision_providers import ProviderError, VisionProviderRegistry


class _OllamaCatalog:
    async def list_models(self, *, refresh: bool = False):
        return []


def _settings(**overrides: str) -> Settings:
    values = {
        "openai_api_key": "",
        "anthropic_api_key": "",
        "gemini_api_key": "",
        "xai_api_key": "",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_catalog_never_exposes_api_keys() -> None:
    registry = VisionProviderRegistry(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
        _OllamaCatalog(),
        _settings(openai_api_key="sk-secret"),
    )

    providers = await registry.list_providers()
    serialized = json.dumps([provider.model_dump() for provider in providers])
    openai = next(provider for provider in providers if provider.id == "openai")

    assert openai.state == "ready"
    assert [model.id for model in openai.models] == ["gpt-5.6-luna", "gpt-5.6-terra"]
    assert "sk-secret" not in serialized
    await registry.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("base_url", "expected_url"),
    [
        ("https://api.openai.com", "https://api.openai.com/v1/responses"),
        ("https://us.api.openai.com/v1", "https://us.api.openai.com/v1/responses"),
    ],
)
async def test_openai_uses_responses_vision_shape(base_url: str, expected_url: str) -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "# Page"}]}
                ],
                "usage": {"input_tokens": 11, "output_tokens": 3},
            },
        )

    registry = VisionProviderRegistry(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        _OllamaCatalog(),
        _settings(openai_api_key="sk-test", openai_base_url=base_url),
    )

    result = await registry.generate("openai", "gpt-5.6-luna", b"png", "Transcribe")

    assert captured["url"] == expected_url
    assert captured["body"]["model"] == "gpt-5.6-luna"
    assert captured["body"]["input"][0]["content"][0]["type"] == "input_image"
    assert result.text == "# Page"
    assert result.input_tokens == 11
    await registry.aclose()


@pytest.mark.asyncio
async def test_openai_text_generation_omits_image_content() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
                "usage": {"input_tokens": 4, "output_tokens": 1},
            },
        )

    registry = VisionProviderRegistry(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        _OllamaCatalog(),
        _settings(openai_api_key="sk-test"),
    )

    result = await registry.generate_text("openai", "gpt-5.6-luna", "Return JSON")

    assert captured["body"]["input"][0]["content"] == [
        {"type": "input_text", "text": "Return JSON"}
    ]
    assert result.text == "{}"
    await registry.aclose()


@pytest.mark.asyncio
async def test_missing_key_is_rejected_before_network_call() -> None:
    registry = VisionProviderRegistry(
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: pytest.fail("network called"))
        ),
        _OllamaCatalog(),
        _settings(),
    )

    with pytest.raises(ProviderError) as caught:
        await registry.generate("anthropic", "claude-sonnet-5", b"png", "Transcribe")

    assert caught.value.code == "provider_not_configured"
    await registry.aclose()


def test_unknown_provider_is_rejected() -> None:
    registry = VisionProviderRegistry(httpx.AsyncClient(), _OllamaCatalog(), _settings())

    with pytest.raises(ProviderError, match="Unknown provider"):
        registry.models_for("ourtoken")


@pytest.mark.asyncio
async def test_glmocr_provider_is_ready_without_an_api_key() -> None:
    registry = VisionProviderRegistry(
        httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200))),
        _OllamaCatalog(),
        _settings(),
    )

    providers = await registry.list_providers()
    glmocr = next(provider for provider in providers if provider.id == "glmocr")

    assert glmocr.state == "ready"
    assert [model.id for model in glmocr.models] == ["glm-ocr"]
    await registry.aclose()


@pytest.mark.asyncio
async def test_glmocr_uses_chat_completions_shape_with_no_auth_header() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        captured["has_auth"] = "authorization" in request.headers
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Invoice number 42"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 6},
            },
        )

    registry = VisionProviderRegistry(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        _OllamaCatalog(),
        _settings(),
    )

    result = await registry.generate("glmocr", "glm-ocr", b"png", "Transcribe")

    assert captured["url"] == "http://localhost:8080/v1/chat/completions"
    assert captured["has_auth"] is False
    assert captured["body"]["model"] == "glm-ocr"
    assert captured["body"]["messages"][0]["content"][0]["type"] == "image_url"
    assert result.text == "Invoice number 42"
    assert result.input_tokens == 120
    await registry.aclose()
