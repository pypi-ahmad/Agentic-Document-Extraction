"""OpenAI Responses API boundary for grounded document extraction."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.logging_setup import get_logger

logger = get_logger("app.parsing.openai_document")


class OpenAIRequestError(RuntimeError):
    pass


class OpenAIUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)


class StructuredGeneration(BaseModel):
    response_id: str | None = None
    value: dict[str, Any]
    usage: OpenAIUsage
    latency_ms: float = Field(ge=0)


def _responses_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return f"{normalized}/responses" if normalized.endswith("/v1") else f"{normalized}/v1/responses"


class OpenAIDocumentAdapter:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com",
    ) -> None:
        self.http = http
        self.api_key = api_key
        self.base_url = base_url

    async def generate_structured(
        self,
        *,
        model: Literal["gpt-5.6-luna", "gpt-5.6-terra"],
        image: bytes | None,
        instructions: str,
        context: str | None = None,
        schema_name: str,
        schema: dict[str, Any],
        reasoning_effort: Literal["none", "low", "medium", "high"],
        detail: Literal["low", "high", "original"],
        prompt_cache_key: str,
    ) -> StructuredGeneration:
        if not self.api_key:
            raise OpenAIRequestError("OpenAI API key is not configured")
        encoded = base64.b64encode(image).decode("ascii") if image is not None else None
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": instructions,
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ]
        if encoded is not None:
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:image/png;base64,{encoded}",
                    "detail": detail,
                }
            )
        if context is not None:
            content.append({"type": "input_text", "text": context})
        payload = {
            "model": model,
            "store": False,
            "reasoning": {"effort": reasoning_effort},
            "prompt_cache_key": prompt_cache_key,
            "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        started = time.perf_counter()
        try:
            response = await self.http.post(
                _responses_url(self.base_url),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            logger.warning("openai_document.request_failed", model=model, error=type(exc).__name__)
            raise OpenAIRequestError("OpenAI document request failed") from exc

        texts: list[str] = []
        refused = False
        for output in body.get("output", []):
            for content in output.get("content", []):
                if content.get("type") == "output_text":
                    texts.append(str(content.get("text", "")))
                elif content.get("type") == "refusal":
                    refused = True
        if refused:
            raise OpenAIRequestError("OpenAI refused the structured document request")
        raw = "".join(texts).strip()
        if not raw:
            raise OpenAIRequestError("OpenAI returned no structured output")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            raise OpenAIRequestError("OpenAI returned invalid structured JSON") from exc
        if not isinstance(value, dict):
            raise OpenAIRequestError("OpenAI structured output must be a JSON object")

        usage_data = body.get("usage") or {}
        input_details = usage_data.get("input_tokens_details") or {}
        usage = OpenAIUsage(
            input_tokens=usage_data.get("input_tokens") or 0,
            output_tokens=usage_data.get("output_tokens") or 0,
            cached_input_tokens=input_details.get("cached_tokens") or 0,
            cache_write_tokens=input_details.get("cache_write_tokens") or 0,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "openai_document.request_complete",
            model=model,
            reasoning_effort=reasoning_effort,
            detail=detail,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_input_tokens=usage.cached_input_tokens,
            cache_write_tokens=usage.cache_write_tokens,
            latency_ms=round(latency_ms, 1),
        )
        return StructuredGeneration(
            response_id=body.get("id"), value=value, usage=usage, latency_ms=latency_ms
        )
