from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers.runtime_capabilities import runtime_capabilities


@pytest.mark.asyncio
async def test_runtime_reports_vision_providers() -> None:
    runtime = SimpleNamespace(
        provider_registry=SimpleNamespace(list_providers=AsyncMock(return_value=[])),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(parser_runtime=runtime)))

    response = await runtime_capabilities(request)

    assert response.model_dump() == {"providers": []}
    runtime.provider_registry.list_providers.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_reports_empty_when_runtime_unavailable() -> None:
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    response = await runtime_capabilities(request)

    assert response.model_dump() == {"providers": []}
