"""Ollama model discovery API."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import require_api_key
from app.services.parsing.model_catalog import OllamaCatalogUnavailable, OllamaModel

router = APIRouter(prefix="/api/ollama", tags=["ollama"], dependencies=[Depends(require_api_key)])


class OllamaModelsResponse(BaseModel):
    models: list[OllamaModel]
    compatible_count: int


@router.get("/models", response_model=OllamaModelsResponse)
async def list_ollama_models(
    request: Request, refresh: bool = Query(False)
) -> OllamaModelsResponse:
    try:
        models = await request.app.state.parser_runtime.model_catalog.list_models(refresh=refresh)
    except OllamaCatalogUnavailable as exc:
        raise HTTPException(
            503, detail={"code": "ollama_unavailable", "message": str(exc)}
        ) from exc
    return OllamaModelsResponse(
        models=models, compatible_count=sum(model.compatible for model in models)
    )
