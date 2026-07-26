from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.routers.runtime_capabilities import runtime_capabilities
from app.services.parsing.paddleocr_docker import PaddleRuntimeStatus


@pytest.mark.asyncio
async def test_runtime_reports_paddleocr_vl_service() -> None:
    runtime = SimpleNamespace(
        paddleocr_vl=SimpleNamespace(
            status=AsyncMock(
                return_value=PaddleRuntimeStatus(
                    available=True,
                    docker_available=True,
                    gpu_available=True,
                    image_present=True,
                    cache_ready=True,
                    image="registry/paddle@sha256:digest",
                )
            )
        ),
        provider_registry=SimpleNamespace(
            list_providers=AsyncMock(return_value=[])
        ),
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(parser_runtime=runtime)))

    response = await runtime_capabilities(request)

    assert response.model_dump() == {
        "paddleocr_vl_available": True,
        "parser_model": "PaddleOCR-VL-1.6",
        "pipeline_version": "v1.6",
        "paddleocr_vl": {
            "available": True,
            "docker_available": True,
            "gpu_available": True,
            "image_present": True,
            "cache_ready": True,
            "image": "registry/paddle@sha256:digest",
            "error": None,
            "pull_command": None,
        },
        "providers": [],
    }
    runtime.paddleocr_vl.status.assert_awaited_once()
    runtime.provider_registry.list_providers.assert_awaited_once()
