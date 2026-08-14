"""Ollama discovery and structured vision adapter."""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from paperplane.openai_document import OpenAIUsage, StructuredGeneration

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True, slots=True)
class OllamaModel:
    name: str
    capabilities: tuple[str, ...]

    @property
    def vision_capable(self) -> bool:
        return "vision" in self.capabilities


class OllamaRequestError(RuntimeError):
    pass


class OllamaDocumentAdapter:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str = DEFAULT_OLLAMA_BASE_URL) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    async def list_models(self) -> list[OllamaModel]:
        try:
            response = await self.http.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            names = [str(item["name"]) for item in response.json().get("models", [])]
            models: list[OllamaModel] = []
            for name in names:
                detail = await self.http.post(f"{self.base_url}/api/show", json={"model": name})
                detail.raise_for_status()
                capabilities = tuple(str(item) for item in detail.json().get("capabilities", []))
                models.append(OllamaModel(name=name, capabilities=capabilities))
            return models
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise OllamaRequestError(
                "Ollama is unavailable or returned an invalid model list"
            ) from exc

    async def generate_structured(
        self,
        *,
        model: str,
        image: bytes | None,
        instructions: str,
        context: str | None = None,
        schema_name: str,
        schema: dict[str, Any],
        reasoning_effort: Literal["none", "low", "medium", "high"],
        detail: Literal["low", "high", "original"],
        prompt_cache_key: str,
    ) -> StructuredGeneration:
        del schema_name, reasoning_effort, detail, prompt_cache_key
        content = instructions
        if context:
            content += f"\n\nPrior/local document context:\n{context}"
        message: dict[str, Any] = {"role": "user", "content": content}
        if image is not None:
            message["images"] = [base64.b64encode(image).decode("ascii")]
        started = time.perf_counter()
        try:
            response = await self.http.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [message],
                    "format": schema,
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
            body = response.json()
            value = json.loads(body["message"]["content"])
            if not isinstance(value, dict):
                raise TypeError("structured response is not an object")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OllamaRequestError("Ollama document request failed") from exc
        return StructuredGeneration(
            response_id=None,
            value=value,
            usage=OpenAIUsage(
                input_tokens=int(body.get("prompt_eval_count", 0)),
                output_tokens=int(body.get("eval_count", 0)),
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )


class ChainedStructuredAdapter:
    """Run Ollama first, then let a cloud adapter validate/refine its structured draft."""

    def __init__(self, local: OllamaDocumentAdapter, cloud: Any, *, cloud_model: str) -> None:
        self.local = local
        self.cloud = cloud
        self.cloud_model = cloud_model

    async def generate_structured(self, **kwargs: Any) -> StructuredGeneration:
        local = await self.local.generate_structured(**kwargs)
        cloud_kwargs = dict(kwargs)
        cloud_kwargs["model"] = self.cloud_model
        local_context = json.dumps(local.value, ensure_ascii=False, separators=(",", ":"))
        existing = cloud_kwargs.get("context")
        cloud_kwargs["context"] = (
            f"{existing}\n\nOllama draft:\n{local_context}"
            if existing
            else f"Ollama draft:\n{local_context}"
        )
        refined = await self.cloud.generate_structured(**cloud_kwargs)
        return StructuredGeneration(
            response_id=refined.response_id,
            value=refined.value,
            usage=OpenAIUsage(
                input_tokens=local.usage.input_tokens + refined.usage.input_tokens,
                output_tokens=local.usage.output_tokens + refined.usage.output_tokens,
                cached_input_tokens=refined.usage.cached_input_tokens,
                cache_write_tokens=refined.usage.cache_write_tokens,
            ),
            latency_ms=local.latency_ms + refined.latency_ms,
        )


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "ChainedStructuredAdapter",
    "OllamaDocumentAdapter",
    "OllamaModel",
    "OllamaRequestError",
]
