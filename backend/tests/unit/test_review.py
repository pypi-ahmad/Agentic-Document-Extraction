import json

import httpx
import pytest

from app.services.parsing.review import OllamaReviewer


@pytest.mark.asyncio
async def test_reviewer_uses_qwen35_structured_vision_output() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "extraction_accuracy": 0.8,
                            "structural_fidelity": 0.9,
                            "completeness": 0.7,
                            "markdown_consistency": 1.0,
                            "reasons": ["one label is unclear"],
                            "regions": [
                                {
                                    "region_id": "p0001-r0001",
                                    "verdict": "warn",
                                    "reason": "label is unclear",
                                    "repair_hint": "re-read the crop",
                                    "risk_flags": ["unclear_label"],
                                }
                            ],
                        }
                    )
                },
                "eval_count": 12,
                "prompt_eval_count": 34,
                "total_duration": 1_000_000,
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://ollama"
    ) as client:
        result = await OllamaReviewer(client, model="qwen3.5:9b").review(
            b"png",
            "# Extracted page",
            ["p0001-r0001"],
            coordinate_manifest={
                "p0001-r0001": {
                    "bbox": [0.1, 0.1, 0.9, 0.3],
                    "type": "text",
                    "text": "Extracted page",
                }
            },
        )

    assert captured["model"] == "qwen3.5:9b"
    assert captured["format"]["type"] == "object"
    assert captured["options"]["temperature"] == 0
    assert captured["messages"][0]["images"]
    assert "Normalized coordinate manifest" in captured["messages"][0]["content"]
    assert "p0001-r0001" in captured["messages"][0]["content"]
    assert result.score.overall == pytest.approx(0.85)
    assert result.regions[0].repair_hint == "re-read the crop"
    assert result.eval_count == 12


@pytest.mark.asyncio
async def test_reviewer_rejects_unknown_region_ids() -> None:
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "message": {
                    "content": json.dumps(
                        {
                            "extraction_accuracy": 1,
                            "structural_fidelity": 1,
                            "completeness": 1,
                            "markdown_consistency": 1,
                            "reasons": [],
                            "regions": [
                                {
                                    "region_id": "invented",
                                    "verdict": "fail",
                                    "reason": "bad",
                                    "repair_hint": None,
                                    "risk_flags": [],
                                }
                            ],
                        }
                    )
                }
            },
        )
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as client:
        result = await OllamaReviewer(client, "vision:test").review(b"png", "text", ["known"])

    assert result.regions == []
