"""Vision provider catalog and normalized generation boundary."""

from __future__ import annotations

import base64
import time
from typing import Literal

import httpx
from pydantic import BaseModel

from app.config import Settings
from app.logging_setup import get_logger

logger = get_logger("app.parsing.vision_providers")


class ProviderError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class VisionModel(BaseModel):
    id: str
    name: str


class VisionProvider(BaseModel):
    id: str
    name: str
    state: Literal["ready", "not_configured", "unavailable"]
    models: list[VisionModel]


class VisionGeneration(BaseModel):
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = 0


_MODELS: dict[str, tuple[str, list[str]]] = {
    "openai": ("OpenAI", ["gpt-5.6-luna", "gpt-5.6-terra"]),
    "anthropic": ("Anthropic", ["claude-sonnet-5", "claude-opus-4-8"]),
    "gemini": ("Google Gemini", ["gemini-3.6-flash", "gemini-3.5-flash-lite"]),
    "xai": ("xAI", ["grok-4.5"]),
}


def _responses_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return f"{normalized}/responses" if normalized.endswith("/v1") else f"{normalized}/v1/responses"


class VisionProviderRegistry:
    def __init__(
        self,
        http: httpx.AsyncClient,
        ollama_catalog,
        settings: Settings,
    ) -> None:
        self.http = http
        self.ollama_catalog = ollama_catalog
        self.settings = settings

    def models_for(self, provider: str) -> list[VisionModel]:
        if provider == "ollama":
            raise ProviderError(
                "dynamic_provider", "Ollama models must be loaded from the runtime catalog"
            )
        if provider not in _MODELS:
            raise ProviderError("provider_not_supported", f"Unknown provider: {provider}")
        return [VisionModel(id=model, name=model) for model in _MODELS[provider][1]]

    async def list_providers(self) -> list[VisionProvider]:
        providers: list[VisionProvider] = []
        try:
            installed = await self.ollama_catalog.list_models()
            local_models = [
                VisionModel(id=model.name, name=model.name)
                for model in installed
                if model.compatible
            ]
            local_state: Literal["ready", "unavailable"] = (
                "ready" if local_models else "unavailable"
            )
        except Exception:
            local_models, local_state = [], "unavailable"
        providers.append(
            VisionProvider(
                id="ollama",
                name="Ollama",
                state=local_state,
                models=local_models,
            )
        )
        for provider, (name, _) in _MODELS.items():
            key = getattr(self.settings, f"{provider}_api_key")
            providers.append(
                VisionProvider(
                    id=provider,
                    name=name,
                    state="ready" if key else "not_configured",
                    models=self.models_for(provider),
                )
            )
        return providers

    async def validate_selection(self, provider: str, model: str) -> None:
        if provider == "ollama":
            try:
                await self.ollama_catalog.require_compatible(model)
            except Exception as exc:
                raise ProviderError(
                    "model_not_available", "Selected Ollama model is unavailable"
                ) from exc
            return
        allowed = {item.id for item in self.models_for(provider)}
        if model not in allowed:
            raise ProviderError("model_not_supported", f"Unsupported {provider} model: {model}")
        if not getattr(self.settings, f"{provider}_api_key"):
            raise ProviderError("provider_not_configured", f"{provider} API key is not configured")

    async def generate(
        self, provider: str, model: str, image: bytes, prompt: str
    ) -> VisionGeneration:
        return await self._generate(provider, model, prompt, image=image)

    async def generate_text(self, provider: str, model: str, prompt: str) -> VisionGeneration:
        return await self._generate(provider, model, prompt, image=None)

    async def _generate(
        self, provider: str, model: str, prompt: str, *, image: bytes | None
    ) -> VisionGeneration:
        if provider == "ollama":
            raise ProviderError(
                "provider_boundary_error", "Ollama generation uses the local adapter"
            )
        allowed = {item.id for item in self.models_for(provider)}
        if model not in allowed:
            raise ProviderError("model_not_supported", f"Unsupported {provider} model: {model}")
        api_key = getattr(self.settings, f"{provider}_api_key")
        if not api_key:
            raise ProviderError("provider_not_configured", f"{provider} API key is not configured")
        encoded = base64.b64encode(image).decode("ascii") if image is not None else None
        started = time.perf_counter()
        try:
            if provider in {"openai", "xai"}:
                base_url = getattr(self.settings, f"{provider}_base_url").rstrip("/")
                response = await self.http.post(
                    _responses_url(base_url),
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": model,
                        "input": [
                            {
                                "role": "user",
                                "content": (
                                    [
                                        {
                                            "type": "input_image",
                                            "image_url": f"data:image/png;base64,{encoded}",
                                        }
                                    ]
                                    if encoded is not None
                                    else []
                                )
                                + [{"type": "input_text", "text": prompt}],
                            }
                        ],
                    },
                )
                response.raise_for_status()
                body = response.json()
                text = "".join(
                    str(content.get("text", ""))
                    for output in body.get("output", [])
                    for content in output.get("content", [])
                    if content.get("type") == "output_text"
                ).strip()
                usage = body.get("usage", {})
                result = VisionGeneration(
                    text=text,
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )
            elif provider == "anthropic":
                response = await self.http.post(
                    f"{self.settings.anthropic_base_url.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    json={
                        "model": model,
                        "max_tokens": 4096,
                        "temperature": 0,
                        "messages": [
                            {
                                "role": "user",
                                "content": (
                                    [
                                        {
                                            "type": "image",
                                            "source": {
                                                "type": "base64",
                                                "media_type": "image/png",
                                                "data": encoded,
                                            },
                                        }
                                    ]
                                    if encoded is not None
                                    else []
                                )
                                + [{"type": "text", "text": prompt}],
                            }
                        ],
                    },
                )
                response.raise_for_status()
                body = response.json()
                text = "".join(
                    str(content.get("text", ""))
                    for content in body.get("content", [])
                    if content.get("type") == "text"
                ).strip()
                usage = body.get("usage", {})
                result = VisionGeneration(
                    text=text,
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                )
            elif provider == "gemini":
                response = await self.http.post(
                    f"{self.settings.gemini_base_url.rstrip('/')}/v1beta/models/"
                    f"{model}:generateContent",
                    headers={"x-goog-api-key": api_key},
                    json={
                        "contents": [
                            {
                                "role": "user",
                                "parts": (
                                    [
                                        {
                                            "inline_data": {
                                                "mime_type": "image/png",
                                                "data": encoded,
                                            }
                                        }
                                    ]
                                    if encoded is not None
                                    else []
                                )
                                + [{"text": prompt}],
                            }
                        ],
                        "generationConfig": {"temperature": 0},
                    },
                )
                response.raise_for_status()
                body = response.json()
                candidates = body.get("candidates", [])
                parts = (
                    candidates[0].get("content", {}).get("parts", [])
                    if candidates and isinstance(candidates[0], dict)
                    else []
                )
                text = "".join(str(part.get("text", "")) for part in parts).strip()
                usage = body.get("usageMetadata", {})
                result = VisionGeneration(
                    text=text,
                    input_tokens=usage.get("promptTokenCount"),
                    output_tokens=usage.get("candidatesTokenCount"),
                )
            else:
                raise ProviderError("provider_not_supported", f"Unknown provider: {provider}")
        except ProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "vision_provider.request_failed",
                provider=provider,
                model=model,
                error_type=type(exc).__name__,
            )
            raise ProviderError(
                "provider_request_failed", f"{provider} vision request failed"
            ) from exc
        if not result.text:
            raise ProviderError("provider_empty_response", f"{provider} returned no text")
        latency_ms = (time.perf_counter() - started) * 1000
        result = result.model_copy(update={"latency_ms": latency_ms})
        logger.info(
            "vision_provider.request_complete",
            provider=provider,
            model=model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=round(latency_ms, 1),
        )
        return result

    async def aclose(self) -> None:
        await self.http.aclose()
