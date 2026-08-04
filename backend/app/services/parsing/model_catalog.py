"""Discovery and capability validation for models installed in Ollama."""

from __future__ import annotations

import asyncio
import time

import httpx
from pydantic import BaseModel, Field


class OllamaCatalogUnavailable(RuntimeError):
    pass


class OllamaModel(BaseModel):
    name: str
    digest: str | None = None
    size: int | None = None
    modified_at: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    compatible: bool = False
    inspection_error: str | None = None


class OllamaModelCatalog:
    def __init__(self, client: httpx.AsyncClient, ttl_seconds: float = 5.0) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self._cached: list[OllamaModel] | None = None
        self._cached_at = 0.0
        self._lock = asyncio.Lock()

    async def list_models(self, *, refresh: bool = False) -> list[OllamaModel]:
        async with self._lock:
            if (
                not refresh
                and self._cached is not None
                and time.monotonic() - self._cached_at < self.ttl_seconds
            ):
                return list(self._cached)
            try:
                response = await self.client.get("/api/tags")
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise OllamaCatalogUnavailable("Ollama is unavailable") from exc
            raw_models = payload.get("models", []) if isinstance(payload, dict) else []
            semaphore = asyncio.Semaphore(4)

            async def inspect(raw: object) -> OllamaModel | None:
                if not isinstance(raw, dict):
                    return None
                name = raw.get("name") or raw.get("model")
                if not isinstance(name, str) or not name.strip():
                    return None
                capabilities: list[str] = []
                error: str | None = None
                try:
                    async with semaphore:
                        shown = await self.client.post("/api/show", json={"model": name})
                        shown.raise_for_status()
                    shown_payload = shown.json()
                    values = (
                        shown_payload.get("capabilities", [])
                        if isinstance(shown_payload, dict)
                        else []
                    )
                    capabilities = sorted(str(value) for value in values if isinstance(value, str))
                except (httpx.HTTPError, ValueError):
                    error = "Capabilities could not be inspected"
                required = {"vision", "completion"}
                return OllamaModel(
                    name=name,
                    digest=raw.get("digest") if isinstance(raw.get("digest"), str) else None,
                    size=raw.get("size") if isinstance(raw.get("size"), int) else None,
                    modified_at=raw.get("modified_at")
                    if isinstance(raw.get("modified_at"), str)
                    else None,
                    capabilities=capabilities,
                    compatible=required.issubset(capabilities),
                    inspection_error=error,
                )

            inspected = await asyncio.gather(*(inspect(raw) for raw in raw_models))
            models = sorted(
                (model for model in inspected if model is not None),
                key=lambda model: model.name.casefold(),
            )
            self._cached = models
            self._cached_at = time.monotonic()
            return list(models)

    async def require_compatible(self, name: str) -> OllamaModel:
        models = await self.list_models()
        model = next((item for item in models if item.name == name), None)
        if model is None:
            raise ValueError("model_not_available")
        if not model.compatible:
            raise ValueError("model_incompatible")
        return model
