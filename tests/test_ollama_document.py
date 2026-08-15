from __future__ import annotations

import json
from io import BytesIO

import httpx
import pytest
from PIL import Image

import paperplane.ollama_document as ollama_document
from paperplane.ollama_document import (
    ChainedStructuredAdapter,
    OllamaDocumentAdapter,
    OllamaRequestError,
)
from paperplane.ollama_ocr import (
    LayoutRegion,
    clean_ocr_output,
    crop_region,
    deduplicate_regions,
    profile_for_family,
)
from paperplane.openai_document import OpenAIUsage, StructuredGeneration


class FakeLayoutDetector:
    def detect(self, _image: bytes) -> list[LayoutRegion]:
        return [
            LayoutRegion("doc_title", 0.99, 0.1, 0.1, 0.9, 0.2),
            LayoutRegion("table", 0.98, 0.1, 0.3, 0.9, 0.8),
        ]


class FakeVisualDetector:
    def detect(self, _image: bytes) -> list[LayoutRegion]:
        return [
            LayoutRegion("text", 0.99, 0.1, 0.1, 0.9, 0.2),
            LayoutRegion("image", 0.99, 0.1, 0.3, 0.9, 0.9),
        ]


class FakeThreeRegionDetector:
    def detect(self, _image: bytes) -> list[LayoutRegion]:
        return [LayoutRegion("text", 0.99, 0.1, top, 0.9, top + 0.1) for top in (0.1, 0.3, 0.5)]


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (100, 100), "white").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_ollama_lists_every_model_and_marks_vision_capability() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200, json={"models": [{"name": "vision:latest"}, {"name": "text:latest"}]}
            )
        model = json.loads(request.content)["model"]
        capabilities = ["completion", "vision"] if model == "vision:latest" else ["completion"]
        family = "glmocr" if model == "vision:latest" else "llama"
        return httpx.Response(
            200, json={"capabilities": capabilities, "details": {"family": family}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        models = await OllamaDocumentAdapter(client).list_models()

    assert [model.name for model in models] == ["vision:latest", "text:latest"]
    assert [model.vision_capable for model in models] == [True, False]
    assert [model.family for model in models] == ["glmocr", "llama"]


@pytest.mark.asyncio
async def test_ollama_uses_native_json_schema_format() -> None:
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        request_body = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "llama"}})
        captured.update(request_body)
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


@pytest.mark.asyncio
async def test_ocr_family_uses_layout_regions_and_native_prompts_without_schema() -> None:
    requests: list[dict] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "glmocr"}})
        requests.append(body)
        prompt = body["messages"][0]["content"]
        content = "Water report" if prompt == "Text Recognition:" else "| Test | Result |"
        return httpx.Response(
            200,
            json={
                "message": {"content": content},
                "prompt_eval_count": 4,
                "eval_count": 3,
                "done_reason": "stop",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OllamaDocumentAdapter(
            client, layout_detector=FakeLayoutDetector()
        ).generate_structured(
            model="glm-ocr:latest",
            image=_png(),
            instructions="generic instructions must not reach OCR",
            schema_name="page_draft_v8",
            schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
            reasoning_effort="none",
            detail="high",
            prompt_cache_key="test",
        )

    assert result.presegmented is True
    assert [request["messages"][0]["content"] for request in requests] == [
        "Text Recognition:",
        "Table Recognition:",
    ]
    assert all("format" not in request for request in requests)
    assert [chunk["type"] for chunk in result.value["chunks"]] == ["title", "table"]
    assert result.value["chunks"][1]["box"] == {
        "left": 0.1,
        "top": 0.3,
        "right": 0.9,
        "bottom": 0.8,
    }
    assert result.usage.input_tokens == 8
    assert result.usage.output_tokens == 6


@pytest.mark.asyncio
async def test_empty_text_is_skipped_and_empty_visual_keeps_its_grounded_figure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "glmocr"}})
        return httpx.Response(200, json={"message": {"content": ""}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OllamaDocumentAdapter(
            client, layout_detector=FakeVisualDetector()
        ).generate_structured(
            model="glm-ocr:latest",
            image=_png(),
            instructions="extract",
            schema_name="page",
            schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
            reasoning_effort="none",
            detail="high",
            prompt_cache_key="test",
        )

    assert result.value["chunks"][0]["text"] == ""
    assert result.value["chunks"][0]["markdown"] == '<figure type="figure"></figure>'


@pytest.mark.asyncio
async def test_deepseek_retries_empty_text_with_strict_prompt_and_counts_usage() -> None:
    prompts: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "deepseekocr"}})
        body = json.loads(request.content)
        prompts.append(body["messages"][0]["content"])
        content = "" if len(prompts) == 1 else "Recovered text"
        return httpx.Response(
            200,
            json={"message": {"content": content}, "prompt_eval_count": 4, "eval_count": 2},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OllamaDocumentAdapter(
            client, layout_detector=FakeThreeRegionDetector()
        ).generate_structured(
            model="deepseek-ocr:latest",
            image=_png(),
            instructions="extract",
            schema_name="page",
            schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
            reasoning_effort="none",
            detail="high",
            prompt_cache_key="test",
        )

    assert prompts[:2] == [
        "Free OCR.",
        "Transcribe all visible text in this crop exactly. Return only the transcription; "
        "do not explain or add Markdown fences.",
    ]
    assert result.usage.input_tokens == 16
    assert result.usage.output_tokens == 8
    assert result.warnings == []


@pytest.mark.asyncio
async def test_deepseek_retries_transient_http_failure(monkeypatch) -> None:
    attempts = 0
    monkeypatch.setattr(ollama_document, "DEEPSEEK_RETRY_DELAY_SECONDS", 0)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "deepseekocr"}})
        attempts += 1
        if attempts == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return httpx.Response(200, json={"message": {"content": "Recovered"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OllamaDocumentAdapter(
            client, layout_detector=FakeThreeRegionDetector()
        ).generate_structured(
            model="deepseek-ocr:latest",
            image=_png(),
            instructions="extract",
            schema_name="page",
            schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
            reasoning_effort="none",
            detail="high",
            prompt_cache_key="test",
        )

    assert attempts == 4
    assert len(result.value["chunks"]) == 3


@pytest.mark.asyncio
async def test_deepseek_skips_one_exhausted_region_and_warns() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "deepseekocr"}})
        attempts += 1
        content = "" if attempts <= 2 else "Usable text"
        return httpx.Response(200, json={"message": {"content": content}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await OllamaDocumentAdapter(
            client, layout_detector=FakeThreeRegionDetector()
        ).generate_structured(
            model="deepseek-ocr:latest",
            image=_png(),
            instructions="extract",
            schema_name="page",
            schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
            reasoning_effort="none",
            detail="high",
            prompt_cache_key="test",
        )

    assert len(result.value["chunks"]) == 2
    assert result.warnings == ["DeepSeek OCR skipped text region 1 after two attempts"]


@pytest.mark.asyncio
async def test_deepseek_aborts_after_three_consecutive_exhausted_regions() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "deepseekocr"}})
        return httpx.Response(200, json={"message": {"content": ""}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OllamaRequestError, match="three consecutive region failures"):
            await OllamaDocumentAdapter(
                client, layout_detector=FakeThreeRegionDetector()
            ).generate_structured(
                model="deepseek-ocr:latest",
                image=_png(),
                instructions="extract",
                schema_name="page",
                schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
                reasoning_effort="none",
                detail="high",
                prompt_cache_key="test",
            )


@pytest.mark.asyncio
async def test_deepseek_does_not_retry_nontransient_http_error() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "deepseekocr"}})
        attempts += 1
        return httpx.Response(400, json={"error": "bad request"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(OllamaRequestError, match="text region 1"):
            await OllamaDocumentAdapter(
                client, layout_detector=FakeThreeRegionDetector()
            ).generate_structured(
                model="deepseek-ocr:latest",
                image=_png(),
                instructions="extract",
                schema_name="page",
                schema={"type": "object", "properties": {"chunks": {"type": "array"}}},
                reasoning_effort="none",
                detail="high",
                prompt_cache_key="test",
            )

    assert attempts == 1


@pytest.mark.asyncio
async def test_chained_adapter_preserves_local_and_cloud_warnings() -> None:
    class FakeAdapter:
        def __init__(self, generation: StructuredGeneration) -> None:
            self.generation = generation

        async def generate_structured(self, **_kwargs) -> StructuredGeneration:
            return self.generation

    local = FakeAdapter(
        StructuredGeneration(
            value={"chunks": []},
            usage=OpenAIUsage(input_tokens=2),
            latency_ms=1,
            warnings=["local warning"],
        )
    )
    cloud = FakeAdapter(
        StructuredGeneration(
            value={"chunks": []},
            usage=OpenAIUsage(output_tokens=3),
            latency_ms=2,
            warnings=["cloud warning"],
        )
    )

    result = await ChainedStructuredAdapter(
        local, cloud, cloud_model="gemini-3.7-flash"
    ).generate_structured(model="deepseek-ocr:latest")

    assert result.warnings == ["local warning", "cloud warning"]
    assert result.usage == OpenAIUsage(input_tokens=2, output_tokens=3)


@pytest.mark.parametrize(
    ("family", "label", "prompt"),
    [
        ("glmocr", "formula", "Formula Recognition:"),
        ("paddleocr", "table", "OCR:"),
        ("deepseekocr", "text", "Free OCR."),
        ("deepseekocr", "table", "<|grounding|>Convert the document to markdown."),
        ("deepseekocr", "image", "Parse the figure."),
    ],
)
def test_ocr_profiles_use_model_native_prompts(family: str, label: str, prompt: str) -> None:
    profile = profile_for_family(family)

    assert profile is not None
    assert profile.prompt_for(label) == prompt


def test_deepseek_protocol_tokens_and_consecutive_duplicates_are_removed() -> None:
    raw = (
        "<|im_end|><|md_start|>Order #: 984<|md_end|><|md_continue|>"
        "<|md_start|>Order #: 984<|md_end|><|md_continue|>"
        "<|md_start|>County: BATES<|md_end|>"
    )

    assert clean_ocr_output(raw) == "Order #: 984\n\nCounty: BATES"


def test_empty_markdown_fence_tail_is_removed() -> None:
    raw = "Environmental Sample Collection Form\n```markdown\n\nEnvironmental Sample Collection Form\n```\n```"

    assert clean_ocr_output(raw) == "Environmental Sample Collection Form"


def test_glm_meta_answer_and_repeated_long_lines_are_removed() -> None:
    raw = (
        "Order #: 984\nType the text: Order #: 984\nIs there any text that can be recognized? Yes\n"
    )

    assert clean_ocr_output(raw) == "Order #: 984"


def test_duplicate_layout_boxes_keep_higher_confidence_without_reordering() -> None:
    regions = [
        LayoutRegion("header", 0.3, 0.1, 0.1, 0.4, 0.2),
        LayoutRegion("image", 0.8, 0.1, 0.1, 0.4, 0.2),
        LayoutRegion("text", 0.9, 0.1, 0.3, 0.9, 0.4),
    ]

    assert deduplicate_regions(regions) == [regions[1], regions[2]]


def test_tall_aside_text_crop_is_rotated_for_recognition() -> None:
    output = BytesIO()
    Image.new("RGB", (100, 300), "white").save(output, format="PNG")
    region = LayoutRegion("aside_text", 0.9, 0.1, 0.1, 0.4, 0.9)

    with Image.open(BytesIO(crop_region(output.getvalue(), region, padding=0))) as crop:
        assert crop.width > crop.height
