import httpx
import pytest

from app.services.parsing.model_catalog import OllamaCatalogUnavailable, OllamaModelCatalog


@pytest.mark.asyncio
async def test_catalog_lists_sorted_models_and_marks_vision_completion_compatible() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": "text:latest", "digest": "b", "size": 2},
                {"name": "vision:latest", "digest": "a", "size": 1},
            ]})
        model = request.read().decode()
        capabilities = ["completion", "vision"] if "vision:latest" in model else ["completion"]
        return httpx.Response(200, json={"capabilities": capabilities})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama") as client:
        result = await OllamaModelCatalog(client).list_models()

    assert [model.name for model in result] == ["text:latest", "vision:latest"]
    assert result[0].compatible is False
    assert result[1].compatible is True


@pytest.mark.asyncio
async def test_catalog_keeps_models_when_show_fails_and_caches_tags() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "broken", "digest": "x"}]})
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama") as client:
        catalog = OllamaModelCatalog(client)
        first = await catalog.list_models()
        second = await catalog.list_models()
        await catalog.list_models(refresh=True)

    assert first == second
    assert first[0].inspection_error
    assert calls == 4


@pytest.mark.asyncio
async def test_catalog_reports_ollama_outage() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://ollama") as client:
        with pytest.raises(OllamaCatalogUnavailable):
            await OllamaModelCatalog(client).list_models()
