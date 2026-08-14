import json

import httpx
import pytest

from paperplane.agnes_document import AGNES_MODEL, AgnesDocumentAdapter
from paperplane.openai_document import capture_audit_calls


@pytest.mark.asyncio
async def test_agnes_uses_chat_completions_with_local_image_data() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl_1",
                "choices": [{"message": {"content": '```json\n{"chunks": []}\n```'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 4},
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AgnesDocumentAdapter(http, api_key="agnes-test")
    calls: list[dict] = []
    with capture_audit_calls(calls):
        result = await adapter.generate_structured(
            model=AGNES_MODEL,
            image=b"png",
            instructions="Extract chunks.",
            schema_name="page_draft",
            schema={"type": "object"},
            reasoning_effort="low",
            detail="high",
            prompt_cache_key="page:v2:shard-0",
        )

    body = captured["body"]
    assert captured["url"] == "https://apihub.agnes-ai.com/v1/chat/completions"
    assert body["model"] == AGNES_MODEL
    assert body["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )
    assert result.value == {"chunks": []}
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4
    assert calls[0]["model"] == AGNES_MODEL
    assert "agnes-test" not in json.dumps(calls)
    assert "data:image" not in json.dumps(calls)
    await http.aclose()
