import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_and_product_info_describe_markdown_parser() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        health = await client.get("/health")
        info = await client.get("/info")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert info.status_code == 200
    assert info.json()["app_name"] == "Paperplane OpenAI Document Pipeline"
    assert info.json()["pipeline"] == [
        "ingest_and_render",
        "luna_page_draft",
        "deterministic_grounding",
        "terra_crop_verification",
        "document_split_and_assembly",
    ]
    assert info.json()["models"] == {
        "draft": "gpt-5.6-luna",
        "verification": "gpt-5.6-terra",
    }
    assert info.json()["local_ai"] is False
    assert info.json()["max_document_pages"] == 500


@pytest.mark.asyncio
async def test_legacy_routes_are_not_registered() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/extractions/" not in paths
    assert "/api/schemas/" not in paths
    assert "/api/v2/jobs" in paths
    assert "/api/parse-jobs" not in paths
    assert "/api/ollama/models" not in paths
