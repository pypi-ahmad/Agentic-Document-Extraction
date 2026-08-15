import json

import httpx
import pytest

from paperplane.gemini_document import GeminiDocumentAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "expected_thinking_level"),
    [
        ("gemini-3.5-flash-lite", "minimal"),
        ("gemini-3.7-flash", "low"),
    ],
)
async def test_gemini_uses_native_multimodal_structured_output(
    model: str, expected_thinking_level: str
) -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers["x-goog-api-key"]
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "responseId": "gemini-response",
                "candidates": [{"content": {"parts": [{"text": '{"chunks": []}'}]}}],
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 3,
                    "cachedContentTokenCount": 2,
                },
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = GeminiDocumentAdapter(http, api_key="gemini-test")
    result = await adapter.generate_structured(
        model=model,
        image=b"png",
        instructions="Extract chunks.",
        schema_name="page_draft",
        schema={"type": "object"},
        reasoning_effort="none",
        detail="high",
        prompt_cache_key="page:v2",
    )

    body = captured["body"]
    assert captured["url"].endswith(f"/models/{model}:generateContent")
    assert captured["key"] == "gemini-test"
    assert body["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
    assert body["generationConfig"]["responseFormat"]["text"] == {
        "mimeType": "APPLICATION_JSON",
        "schema": {"type": "object"},
    }
    assert body["generationConfig"]["thinkingConfig"] == {"thinkingLevel": expected_thinking_level}
    assert result.value == {"chunks": []}
    assert result.usage.cached_input_tokens == 2
    await http.aclose()
