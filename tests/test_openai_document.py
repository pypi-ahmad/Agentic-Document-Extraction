import json

import httpx
import pytest

from paperplane.openai_document import (
    OpenAIDocumentAdapter,
    OpenAIRequestError,
    capture_audit_calls,
)

PAGE_SCHEMA = {
    "type": "object",
    "properties": {"chunks": {"type": "array", "items": {"type": "object"}}},
    "required": ["chunks"],
    "additionalProperties": False,
}


@pytest.mark.asyncio
async def test_page_draft_uses_strict_cached_responses_contract() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"chunks": []}'}],
                    }
                ],
                "usage": {
                    "input_tokens": 1200,
                    "output_tokens": 40,
                    "input_tokens_details": {
                        "cached_tokens": 1024,
                        "cache_write_tokens": 0,
                    },
                },
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIDocumentAdapter(http, api_key="sk-test", base_url="https://api.openai.com")

    calls: list[dict] = []
    with capture_audit_calls(calls):
        result = await adapter.generate_structured(
            model="gpt-5.6-luna",
            image=b"png",
            instructions="Extract ordered grounded chunks.",
            schema_name="page_draft",
            schema=PAGE_SCHEMA,
            reasoning_effort="low",
            detail="high",
            prompt_cache_key="page-draft:v2:shard-0",
        )

    body = captured["body"]
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert body["model"] == "gpt-5.6-luna"
    assert body["store"] is False
    assert body["reasoning"] == {"effort": "low"}
    assert body["text"]["format"] == {
        "type": "json_schema",
        "name": "page_draft",
        "strict": True,
        "schema": PAGE_SCHEMA,
    }
    assert body["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert body["input"][0]["content"][0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert body["input"][0]["content"][1]["detail"] == "high"
    assert "temperature" not in body
    assert result.value == {"chunks": []}
    assert result.usage.cached_input_tokens == 1024
    assert result.usage.cache_write_tokens == 0
    assert calls[0]["status"] == "completed"
    assert calls[0]["value"] == {"chunks": []}
    assert calls[0]["image_sha256"]
    assert "sk-test" not in json.dumps(calls)
    assert "data:image" not in json.dumps(calls)
    await http.aclose()


@pytest.mark.asyncio
async def test_crop_verification_uses_original_detail() -> None:
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

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIDocumentAdapter(http, api_key="sk-test")

    await adapter.generate_structured(
        model="gpt-5.6-terra",
        image=b"crop",
        instructions="Read the crop independently.",
        schema_name="crop_verification",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        reasoning_effort="high",
        detail="original",
        prompt_cache_key="crop:v2:shard-0",
    )

    assert captured["body"]["input"][0]["content"][1]["detail"] == "original"
    await http.aclose()


@pytest.mark.asyncio
async def test_refusal_is_not_treated_as_structured_output() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIDocumentAdapter(http, api_key="sk-test")

    with pytest.raises(OpenAIRequestError, match="refused"):
        await adapter.generate_structured(
            model="gpt-5.6-luna",
            image=b"png",
            instructions="Extract.",
            schema_name="page",
            schema=PAGE_SCHEMA,
            reasoning_effort="low",
            detail="high",
            prompt_cache_key="page:v2:shard-0",
        )
    await http.aclose()


@pytest.mark.asyncio
async def test_document_reduction_places_dynamic_context_after_cache_breakpoint() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}]
            },
        )

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OpenAIDocumentAdapter(http, api_key="sk-test")

    await adapter.generate_structured(
        model="gpt-5.6-terra",
        image=None,
        instructions="Build the grounded document hierarchy.",
        context='<a id="p0001-c0001"></a> Invoice INV-42',
        schema_name="document_reduction",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        reasoning_effort="high",
        detail="original",
        prompt_cache_key="reduce:v2:shard-0",
    )

    content = captured["body"]["input"][0]["content"]
    assert content[0]["prompt_cache_breakpoint"] == {"mode": "explicit"}
    assert content[1] == {
        "type": "input_text",
        "text": '<a id="p0001-c0001"></a> Invoice INV-42',
    }
    assert all(item["type"] != "input_image" for item in content)
    await http.aclose()
