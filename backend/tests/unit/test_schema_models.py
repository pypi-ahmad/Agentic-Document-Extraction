import json

import httpx
import pytest

from app.services.parsing.schema_models import SchemaModelClient
from app.services.parsing.vision_providers import VisionGeneration


class _CloudRegistry:
    calls: list[tuple[str, str, str]]

    def __init__(self) -> None:
        self.calls = []

    async def generate_text(self, provider: str, model: str, prompt: str) -> VisionGeneration:
        self.calls.append((provider, model, prompt))
        return VisionGeneration(
            text='{"data":{"invoice_number":"INV-1"},"evidence":{"/invoice_number":["r1"]},"confidence":{"/invoice_number":0.9}}',
            input_tokens=10,
            output_tokens=5,
            latency_ms=12,
        )


@pytest.mark.asyncio
async def test_ollama_schema_model_uses_native_json_schema_format() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "role": "assistant",
                    "content": '{"data":{"invoice_number":"INV-1"},"evidence":{"/invoice_number":["r1"]},"confidence":{"/invoice_number":0.8}}',
                },
                "prompt_eval_count": 20,
                "eval_count": 8,
            },
        )

    http = httpx.AsyncClient(
        base_url="http://localhost:11434", transport=httpx.MockTransport(handler)
    )
    client = SchemaModelClient(http, _CloudRegistry())  # type: ignore[arg-type]
    result = await client.generate(
        provider="ollama",
        model="qwen3.5:9b",
        prompt="Extract",
        data_schema={
            "type": "object",
            "properties": {"invoice_number": {"type": "string"}},
            "additionalProperties": False,
        },
    )

    assert captured["format"]["properties"]["data"]["properties"]["invoice_number"]
    assert captured["stream"] is False
    assert captured["keep_alive"] == 0
    assert result.data == {"invoice_number": "INV-1"}
    assert result.input_tokens == 20
    await http.aclose()


@pytest.mark.asyncio
async def test_cloud_schema_model_uses_text_provider_boundary() -> None:
    registry = _CloudRegistry()
    http = httpx.AsyncClient()
    client = SchemaModelClient(http, registry)  # type: ignore[arg-type]

    result = await client.generate(
        provider="openai",
        model="gpt-5.6-luna",
        prompt="Extract",
        data_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )

    assert registry.calls == [("openai", "gpt-5.6-luna", "Extract")]
    assert result.evidence == {"/invoice_number": ["r1"]}
    assert result.latency_ms == 12
    await http.aclose()
