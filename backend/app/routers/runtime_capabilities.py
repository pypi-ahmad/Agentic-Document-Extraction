"""Primary parser runtime capability API."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import require_api_key
from app.services.parsing.paddleocr_docker import (
    PaddleOCRVLDockerRunner,
    PaddleRuntimeStatus,
)
from app.services.parsing.vision_providers import VisionProvider

router = APIRouter(
    prefix="/api/runtime", tags=["runtime"], dependencies=[Depends(require_api_key)]
)


class RuntimeCapabilitiesResponse(BaseModel):
    paddleocr_vl_available: bool
    parser_model: str
    pipeline_version: str
    paddleocr_vl: PaddleRuntimeStatus
    providers: list[VisionProvider]


@router.get("/capabilities", response_model=RuntimeCapabilitiesResponse)
async def runtime_capabilities(request: Request) -> RuntimeCapabilitiesResponse:
    runtime = getattr(request.app.state, "parser_runtime", None)
    status = (
        await runtime.paddleocr_vl.status()
        if runtime is not None
        else PaddleRuntimeStatus(
            available=False,
            image="",
            error="Parser runtime is unavailable",
        )
    )
    return RuntimeCapabilitiesResponse(
        paddleocr_vl_available=status.available,
        parser_model=PaddleOCRVLDockerRunner.model_name,
        pipeline_version=PaddleOCRVLDockerRunner.pipeline_version,
        paddleocr_vl=status,
        providers=(
            await runtime.provider_registry.list_providers()
            if runtime is not None
            else []
        ),
    )
