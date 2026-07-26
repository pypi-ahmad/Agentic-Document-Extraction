"""Dedicated local or cloud model boundary for schema extraction."""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.logging_setup import get_logger
from app.services.parsing.vision_providers import ProviderError, VisionProviderRegistry

logger = get_logger("app.parsing.schema_models")


class SchemaModelError(RuntimeError):
    pass


class SchemaModelGeneration(BaseModel):
    data: dict[str, Any]
    evidence: dict[str, list[str]] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float = Field(default=0, ge=0)


class SchemaModelClient:
    def __init__(self, ollama: httpx.AsyncClient, providers: VisionProviderRegistry) -> None:
        self.ollama = ollama
        self.providers = providers

    async def generate(
        self,
        *,
        provider: str,
        model: str,
        prompt: str,
        data_schema: dict[str, Any],
    ) -> SchemaModelGeneration:
        started = time.perf_counter()
        try:
            if provider == "ollama":
                response = await self.ollama.post(
                    "/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "format": _response_schema(data_schema),
                        "stream": False,
                        "keep_alive": 0,
                        "options": {"temperature": 0},
                    },
                )
                response.raise_for_status()
                body = response.json()
                content = body.get("message", {}).get("content", "")
                input_tokens = body.get("prompt_eval_count")
                output_tokens = body.get("eval_count")
                provider_latency = 0.0
            else:
                generated = await self.providers.generate_text(provider, model, prompt)
                content = generated.text
                input_tokens = generated.input_tokens
                output_tokens = generated.output_tokens
                provider_latency = generated.latency_ms
            payload = json.loads(content)
            parsed = SchemaModelGeneration.model_validate(
                {
                    **payload,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "latency_ms": provider_latency
                    or (time.perf_counter() - started) * 1000,
                }
            )
        except SchemaModelError:
            raise
        except (httpx.HTTPError, ProviderError, ValidationError, ValueError, TypeError) as exc:
            logger.warning(
                "schema_model.request_failed",
                provider=provider,
                model=model,
                error_type=type(exc).__name__,
            )
            raise SchemaModelError(f"{provider} schema extraction failed") from exc
        logger.info(
            "schema_model.request_complete",
            provider=provider,
            model=model,
            input_tokens=parsed.input_tokens,
            output_tokens=parsed.output_tokens,
            latency_ms=round(parsed.latency_ms, 1),
        )
        return parsed


def _response_schema(data_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "data": data_schema,
            "evidence": {
                "type": "object",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
            "confidence": {
                "type": "object",
                "additionalProperties": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
        "required": ["data", "evidence", "confidence"],
        "additionalProperties": False,
    }
