"""Google Gemini Generate Content boundary for grounded document extraction."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from typing import Any, Literal, cast

import httpx

from paperplane.openai_document import (
    OpenAIRequestError,
    OpenAIUsage,
    StructuredGeneration,
    _emit_audit,
)

logger = logging.getLogger("paperplane.gemini_document")

DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODELS = {"gemini-3.5-flash-lite", "gemini-3.6-flash"}


class GeminiRequestError(OpenAIRequestError):
    """Raised when Gemini cannot return a structured document result."""


class GeminiDocumentAdapter:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
    ) -> None:
        self.http = http
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

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
        del detail
        if model not in GEMINI_MODELS:
            raise GeminiRequestError(f"Unsupported Gemini model: {model}")
        audit_record: dict[str, Any] = {
            "model": model,
            "schema_name": schema_name,
            "schema_sha256": hashlib.sha256(
                json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "instructions": instructions,
            "context": context,
            "reasoning_effort": reasoning_effort,
            "prompt_cache_key": prompt_cache_key,
            "image_sha256": hashlib.sha256(image).hexdigest() if image is not None else None,
        }
        if not self.api_key:
            _emit_audit({**audit_record, "status": "error", "error_type": "missing_api_key"})
            raise GeminiRequestError("Gemini API key is not configured")

        parts: list[dict[str, Any]] = []
        if image is not None:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": base64.b64encode(image).decode("ascii"),
                    }
                }
            )
        prompt = (
            instructions if context is None else f"{instructions}\n\nDocument context:\n{context}"
        )
        parts.append({"text": prompt})
        thinking_level = "minimal" if reasoning_effort == "none" else reasoning_effort
        payload = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseFormat": {
                    "text": {
                        "mimeType": "application/json",
                        "schema": schema,
                    }
                },
                "thinkingConfig": {"thinkingLevel": thinking_level},
            },
        }

        started = time.perf_counter()
        try:
            response = await self.http.post(
                f"{self.base_url}/models/{model}:generateContent",
                headers={"x-goog-api-key": self.api_key},
                json=payload,
            )
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            candidates = cast(list[dict[str, Any]], body["candidates"])
            content = cast(dict[str, Any], candidates[0]["content"])
            response_parts = cast(list[dict[str, Any]], content["parts"])
            raw = "".join(str(part.get("text", "")) for part in response_parts).strip()
            value_data: Any = json.loads(raw)
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            _emit_audit(
                {
                    **audit_record,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            logger.warning("Gemini document request failed: %s", type(exc).__name__)
            raise GeminiRequestError("Gemini document request failed") from exc
        if not isinstance(value_data, dict):
            _emit_audit({**audit_record, "status": "error", "error_type": "non_object"})
            raise GeminiRequestError("Gemini structured output must be a JSON object")
        value = cast(dict[str, Any], value_data)

        raw_usage = body.get("usageMetadata")
        usage_data = cast(dict[str, Any], raw_usage) if isinstance(raw_usage, dict) else {}
        usage = OpenAIUsage(
            input_tokens=usage_data.get("promptTokenCount") or 0,
            output_tokens=usage_data.get("candidatesTokenCount") or 0,
            cached_input_tokens=usage_data.get("cachedContentTokenCount") or 0,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        response_id = str(body["responseId"]) if body.get("responseId") else None
        _emit_audit(
            {
                **audit_record,
                "status": "completed",
                "response_id": response_id,
                "value": value,
                "usage": usage.model_dump(),
                "latency_ms": latency_ms,
            }
        )
        return StructuredGeneration(
            response_id=response_id,
            value=value,
            usage=usage,
            latency_ms=latency_ms,
        )


__all__ = [
    "DEFAULT_GEMINI_BASE_URL",
    "GEMINI_MODELS",
    "GeminiDocumentAdapter",
    "GeminiRequestError",
]
