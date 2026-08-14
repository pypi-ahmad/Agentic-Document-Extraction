from __future__ import annotations

import json

import httpx
import pytest

from paperplane.ollama_document import OllamaDocumentAdapter


@pytest.mark.asyncio
async def test_ollama_lists_every_model_and_marks_vision_capability() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "vision:latest"}, {"name": "text:latest"}]}
            )
        model = json.loads(request.content)["model"]
        capabilities = ["completion", "vision"] if model == "vision:latest" else ["completion"]
        return httpx.Response(200, json={"capabilities": capabilities})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        models = await OllamaDocumentAdapter(client).list_models()

    assert [model.name for model in models] == ["vision:latest", "text:latest"]
    assert [model.vision_capable for model in models] == [True, False]


@pytest.mark.asyncio
async def test_ollama_uses_native_json_schema_format() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"content": json.dumps({"value": "ok"})},
                "prompt_eval_count": 10,
                "eval_count": 2,
            },
        )

    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OllamaDocumentAdapter(client).generate_structured(
            model="vision:latest",
            image=b"image",
            instructions="Extract",
            schema_name="result",
            schema=schema,
            reasoning_effort="none",
            detail="high",
            prompt_cache_key="test",
        )

    assert captured["format"] == schema
    assert captured["stream"] is False
    assert result.value == {"value": "ok"}
    assert result.usage.input_tokens == 10
