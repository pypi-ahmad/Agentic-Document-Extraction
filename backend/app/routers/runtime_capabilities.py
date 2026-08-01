"""Primary parser runtime capability API."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.auth import require_api_key
from app.services.parsing.vision_providers import VisionProvider

router = APIRouter(
    prefix="/api/runtime", tags=["runtime"], dependencies=[Depends(require_api_key)]
)


class RuntimeCapabilitiesResponse(BaseModel):
    providers: list[VisionProvider]


@router.get("/capabilities", response_model=RuntimeCapabilitiesResponse)
async def runtime_capabilities(request: Request) -> RuntimeCapabilitiesResponse:
    runtime = getattr(request.app.state, "parser_runtime", None)
    return RuntimeCapabilitiesResponse(
        providers=(
            await runtime.provider_registry.list_providers()
            if runtime is not None
            else []
        ),
    )
