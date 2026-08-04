import json
from pathlib import Path

import httpx
import pytest

from app.services.parsing.glmocr_layout_engine import (
    GlmOcrLayoutEngine,
    GlmOcrResponseError,
    GlmOcrUnavailable,
)


def _page_png(tmp_path: Path, name: str) -> Path:
    from PIL import Image

    path = tmp_path / name
    Image.new("RGB", (100, 100), "white").save(path)
    return path


@pytest.mark.asyncio
async def test_segment_document_maps_regions_and_normalizes_bbox(tmp_path) -> None:
    page1 = _page_png(tmp_path, "p1.png")
    page2 = _page_png(tmp_path, "p2.png")
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "json_result": [
                    [
                        {
                            "index": 0,
                            "label": "text",
                            "content": "Hello",
                            "bbox_2d": [100, 200, 900, 300],
                        }
                    ],
                    [
                        {
                            "index": 0,
                            "label": "table",
                            "content": "<table><tr><td>A</td><td>B</td></tr></table>",
                            "bbox_2d": [0, 0, 1000, 1000],
                        }
                    ],
                ]
            },
        )

    engine = GlmOcrLayoutEngine(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), "http://localhost:5002"
    )

    pages = await engine.segment_document(
        job_id="job", image_paths=[page1, page2], page_numbers=[1, 2], work_dir=tmp_path
    )

    assert captured["body"]["images"][0].startswith("data:image/png;base64,")
    assert len(pages[1]) == 1 and pages[1][0].type == "text" and pages[1][0].content == "Hello"
    assert pages[1][0].bbox.left == pytest.approx(0.1)
    assert pages[1][0].bbox.right == pytest.approx(0.9)
    assert pages[2][0].type == "table"
    assert pages[2][0].table_rows == [["A", "B"]]
    assert pages[2][0].source == "glmocr"


@pytest.mark.asyncio
async def test_unknown_label_falls_back_to_text(tmp_path) -> None:
    page = _page_png(tmp_path, "p1.png")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "json_result": [
                    [
                        {
                            "index": 0,
                            "label": "doc_title",
                            "content": "Title",
                            "bbox_2d": [0, 0, 500, 50],
                        }
                    ]
                ]
            },
        )

    engine = GlmOcrLayoutEngine(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), "http://localhost:5002"
    )

    pages = await engine.segment_document(
        job_id="job", image_paths=[page], page_numbers=[1], work_dir=tmp_path
    )

    assert pages[1][0].type == "text"
    assert pages[1][0].source_label == "doc_title"


@pytest.mark.asyncio
async def test_connection_failure_raises_unavailable(tmp_path) -> None:
    page = _page_png(tmp_path, "p1.png")

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    engine = GlmOcrLayoutEngine(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), "http://localhost:5002"
    )

    with pytest.raises(GlmOcrUnavailable):
        await engine.segment_document(
            job_id="job", image_paths=[page], page_numbers=[1], work_dir=tmp_path
        )


@pytest.mark.asyncio
async def test_page_count_mismatch_raises_response_error(tmp_path) -> None:
    page1 = _page_png(tmp_path, "p1.png")
    page2 = _page_png(tmp_path, "p2.png")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"json_result": [[]]})

    engine = GlmOcrLayoutEngine(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), "http://localhost:5002"
    )

    with pytest.raises(GlmOcrResponseError):
        await engine.segment_document(
            job_id="job", image_paths=[page1, page2], page_numbers=[1, 2], work_dir=tmp_path
        )
