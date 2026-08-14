import json
from hashlib import sha256
from io import BytesIO

import httpx
import pytest
from PIL import Image

from paperplane.agnes_document import AGNES_MODEL, AgnesDocumentAdapter, AgnesRequestError
from paperplane.annotated_pdf import build_annotated_pdf
from paperplane.contracts import assemble_parse_response
from paperplane.ingest import RenderedPage
from paperplane.openai_document import capture_audit_calls
from paperplane.parser import _agentic_page
from paperplane.pipeline import PAGE_DRAFT_SCHEMA, V2PageProcessor
from paperplane.pipeline_contracts import ProcessingMode


def _tool_response(
    arguments: dict, *, response_id: str = "chatcmpl_1", function_name: str = "page_draft"
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": response_id,
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "type": "function",
                                "function": {
                                    "name": function_name,
                                    "arguments": json.dumps(arguments),
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )


def _content_response(value: dict, *, response_id: str = "chatcmpl_content") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": response_id,
            "choices": [{"message": {"content": f"```json\n{json.dumps(value)}\n```"}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        },
    )


def _chunk(box: dict[str, float]) -> dict:
    return {
        "type": "text",
        "text": "Invoice total 42.00",
        "markdown": "Invoice total 42.00",
        "box": box,
        "parent_order": None,
        "atomic_lines": [],
        "row": None,
        "col": None,
        "rowspan": None,
        "colspan": None,
    }


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_agnes_uses_chat_completions_for_text_workflows() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return _tool_response({"chunks": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = AgnesDocumentAdapter(http, api_key="agnes-test")
    calls: list[dict] = []
    with capture_audit_calls(calls):
        result = await adapter.generate_structured(
            model=AGNES_MODEL,
            image=None,
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
    assert len(body["messages"][0]["content"]) == 1
    assert body["tools"][0]["function"]["parameters"] == {"type": "object"}
    assert body["tool_choice"]["function"]["name"] == "page_draft"
    assert result.value == {"chunks": []}
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 4
    assert calls[0]["model"] == AGNES_MODEL
    assert "agnes-test" not in json.dumps(calls)
    assert "data:image" not in json.dumps(calls)
    await http.aclose()


@pytest.mark.asyncio
async def test_agnes_sends_private_visual_inputs_as_data_urls() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _tool_response({"chunks": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        adapter = AgnesDocumentAdapter(http, api_key="agnes-test")
        await adapter.generate_structured(
            model=AGNES_MODEL,
            image=b"private",
            instructions="Extract chunks.",
            schema_name="page_draft",
            schema={"type": "object"},
            reasoning_effort="low",
            detail="high",
            prompt_cache_key="page:v2:shard-0",
        )

    content = captured["body"]["messages"][0]["content"]
    assert content[0] == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,cHJpdmF0ZQ=="},
    }


@pytest.mark.asyncio
async def test_agnes_retries_reversed_geometry_and_counts_all_usage() -> None:
    requests: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        box = (
            {"left": 0.8, "top": 0.1, "right": 0.2, "bottom": 0.4}
            if len(requests) == 1
            else {"left": 0.1, "top": 0.1, "right": 0.8, "bottom": 0.4}
        )
        return _tool_response({"chunks": [_chunk(box)]}, response_id=f"attempt-{len(requests)}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await AgnesDocumentAdapter(http, api_key="agnes-test").generate_structured(
            model=AGNES_MODEL,
            image=b"private",
            instructions="Extract chunks.",
            schema_name="page_draft",
            schema=PAGE_DRAFT_SCHEMA,
            reasoning_effort="low",
            detail="high",
            prompt_cache_key="page:v2:shard-0",
        )

    assert len(requests) == 2
    assert (
        "Previous structured response was invalid"
        in requests[1]["messages"][0]["content"][-1]["text"]
    )
    assert result.value["chunks"][0]["box"]["left"] == 0.1
    assert result.response_id == "attempt-2"
    assert result.usage.input_tokens == 24
    assert result.usage.output_tokens == 8


@pytest.mark.asyncio
async def test_agnes_normalizes_provider_shorthand_before_validation() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _content_response(
            {
                "chunks": [
                    {
                        "type": "text",
                        "text": "Invoice total 42.00",
                        "box": {"left": 100, "top": 100, "right": 800, "bottom": 400},
                    }
                ]
            }
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await AgnesDocumentAdapter(http, api_key="agnes-test").generate_structured(
            model=AGNES_MODEL,
            image=b"private",
            instructions="Extract chunks.",
            schema_name="page_draft_v8",
            schema=PAGE_DRAFT_SCHEMA,
            reasoning_effort="low",
            detail="high",
            prompt_cache_key="page:v2:shard-0",
        )

    chunk = result.value["chunks"][0]
    assert chunk["markdown"] == "Invoice total 42.00"
    assert chunk["atomic_lines"] == []
    assert chunk["parent_order"] is None
    assert chunk["row"] is None
    assert chunk["box"] == {"left": 0.1, "top": 0.1, "right": 0.8, "bottom": 0.4}


@pytest.mark.asyncio
async def test_agnes_fails_after_two_invalid_structured_responses() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return _tool_response({"chunks": [{"text": "missing required fields"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        adapter = AgnesDocumentAdapter(http, api_key="agnes-test")
        with pytest.raises(AgnesRequestError, match="valid structured output"):
            await adapter.generate_structured(
                model=AGNES_MODEL,
                image=b"private",
                instructions="Extract chunks.",
                schema_name="page_draft",
                schema=PAGE_DRAFT_SCHEMA,
                reasoning_effort="low",
                detail="high",
                prompt_cache_key="page:v2:shard-0",
            )

    assert attempts == 2


@pytest.mark.asyncio
async def test_agnes_geometry_reaches_the_annotated_pdf() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return _content_response(
            {"chunks": [_chunk({"left": 0.1, "top": 0.1, "right": 0.8, "bottom": 0.4})]}
        )

    image = _png()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        processor = V2PageProcessor(
            AgnesDocumentAdapter(http, api_key="agnes-test"), model=AGNES_MODEL
        )
        page_result = await processor.process_page(
            source=image,
            filename="invoice.png",
            source_sha256=sha256(image).hexdigest(),
            page=RenderedPage(1, image, 100, 100, []),
            mode=ProcessingMode.ECONOMY,
        )

    response = assemble_parse_response(
        document_id="doc-1",
        job_id="job-1",
        model="paperplane-ade-fast-latest",
        ai_model=AGNES_MODEL,
        pages=[_agentic_page(page_result, parser="agnes_vision")],
        engine="agnes_vision",
    )
    artifact = build_annotated_pdf(source=image, filename="invoice.png", response=response)

    assert artifact.kind == "source_overlay"
    assert artifact.annotated_blocks == 1
