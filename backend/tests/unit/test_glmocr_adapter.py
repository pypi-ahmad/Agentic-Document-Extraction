import httpx
import pytest
from PIL import Image

from app.services.parsing.contracts import BoundingBox, Region
from app.services.parsing.engines import VisionZoneEngine
from app.services.parsing.glmocr_adapter import GLMOCRAdapter, GLMOCRUnavailable


@pytest.mark.asyncio
async def test_readiness_returns_local_model_digest() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200, json={"models": [{"name": "glm-ocr:latest", "digest": "abc"}]}
        )
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as client:
        result = await GLMOCRAdapter(client, "glm-ocr:latest").readiness()
    assert result.ready and result.digest == "abc"


@pytest.mark.asyncio
async def test_recognize_calls_ollama_without_cloud_sdk() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"response": "| A | B |", "eval_count": 5})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama"
    ) as client:
        result = await GLMOCRAdapter(client, "glm-ocr:latest").recognize(b"png", "table")
    assert "Markdown table" in captured["prompt"]
    assert result.text == "| A | B |"


@pytest.mark.asyncio
async def test_recognize_rejects_empty_output() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={"response": ""}))
    async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as client:
        with pytest.raises(GLMOCRUnavailable):
            await GLMOCRAdapter(client, "glm-ocr:latest").recognize(b"png", "text")


@pytest.mark.asyncio
async def test_local_recognition_preserves_paddle_candidate_and_geometry(tmp_path) -> None:
    image_path = tmp_path / "page.png"
    Image.new("RGB", (100, 100), "white").save(image_path)
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"response": "Correct local transcription"})
    )
    original = Region(
        id="p0001-r0001",
        type="text",
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
        content="Paddle candidate",
        source="paddleocr_vl",
        order=2,
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as client:
        result = await VisionZoneEngine(client, None).process(  # type: ignore[arg-type]
            image_path, original, model="glm-ocr:latest"
        )

    assert result.id == original.id
    assert result.bbox == original.bbox
    assert result.order == original.order
    assert result.content == "Correct local transcription"
    assert [candidate.source for candidate in result.recognition_candidates] == [
        "paddleocr_vl",
        "glm_ocr",
    ]
    assert result.recognition_candidates[-1].model == "glm-ocr:latest"
    assert result.recognition_candidates[-1].selected is True
    assert "recognition_disagreement" in result.warnings
