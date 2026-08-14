import json

import httpx
import pytest

from paperplane.anthropic_document import ANTHROPIC_MODEL, AnthropicDocumentAdapter


@pytest.mark.asyncio
async def test_anthropic_uses_messages_vision_and_json_schema() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "content": [{"type": "text", "text": '{"chunks": []}'}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AnthropicDocumentAdapter(http, api_key="anthropic-test")
    result = await adapter.generate_structured(
        model=ANTHROPIC_MODEL,
        image=b"png",
        instructions="Extract chunks.",
        schema_name="page_draft",
        schema={"type": "object"},
        reasoning_effort="high",
        detail="original",
        prompt_cache_key="page:v2",
    )

    body = captured["body"]
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "anthropic-test"
    assert body["model"] == "claude-sonnet-5"
    assert body["messages"][0]["content"][0]["type"] == "image"
    assert body["output_config"] == {
        "effort": "high",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert body["thinking"] == {"type": "adaptive"}
    assert result.value == {"chunks": []}
    await http.aclose()
