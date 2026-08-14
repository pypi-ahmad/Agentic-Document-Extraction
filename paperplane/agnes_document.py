"""Agnes Chat Completions boundary for grounded document extraction."""

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

logger = logging.getLogger("paperplane.agnes_document")

AGNES_MODEL = "agnes-2.5-flash"
DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"


class AgnesRequestError(OpenAIRequestError):
    """Raised when Agnes cannot return a structured document result."""


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return (
        f"{normalized}/chat/completions"
        if normalized.endswith("/v1")
        else f"{normalized}/v1/chat/completions"
    )


def _json_text(value: str) -> str:
    raw = value.strip()
    if raw.startswith("```") and raw.endswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:-1]).strip()
    return raw


class AgnesDocumentAdapter:
    """Adapt the pipeline's structured-generation contract to Agnes 2.5 Flash."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = DEFAULT_AGNES_BASE_URL,
    ) -> None:
        self.http = http
        self.api_key = api_key
        self.base_url = base_url

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
        if model != AGNES_MODEL:
            raise AgnesRequestError(f"Unsupported Agnes model: {model}")
        audit_record: dict[str, Any] = {
            "model": AGNES_MODEL,
            "schema_name": schema_name,
            "schema_sha256": hashlib.sha256(
                json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "instructions": instructions,
            "context": context,
            "reasoning_effort": reasoning_effort,
            "detail": detail,
            "prompt_cache_key": prompt_cache_key,
            "image_sha256": hashlib.sha256(image).hexdigest() if image is not None else None,
        }
        if not self.api_key:
            _emit_audit({**audit_record, "status": "error", "error_type": "missing_api_key"})
            raise AgnesRequestError("Agnes API key is not configured")
        prompt_parts = [
            instructions,
            f"Return only one JSON object named {schema_name} that matches this JSON Schema:",
            json.dumps(schema, separators=(",", ":")),
        ]
        if context is not None:
            prompt_parts.extend(["Document context:", context])
        content: list[dict[str, Any]] = []
        if image is not None:
            encoded = base64.b64encode(image).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{encoded}"},
                }
            )
        content.append({"type": "text", "text": "\n\n".join(prompt_parts)})
        payload: dict[str, Any] = {
            "model": AGNES_MODEL,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 16_384,
            "stream": False,
        }

        started = time.perf_counter()
        try:
            response = await self.http.post(
                _chat_completions_url(self.base_url),
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            raw = _json_text(str(body["choices"][0]["message"]["content"]))
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
            logger.warning("Agnes document request failed: %s", type(exc).__name__)
            raise AgnesRequestError("Agnes document request failed") from exc
        if not isinstance(value_data, dict):
            _emit_audit({**audit_record, "status": "error", "error_type": "non_object"})
            raise AgnesRequestError("Agnes structured output must be a JSON object")
        value = cast(dict[str, Any], value_data)

        raw_usage = body.get("usage")
        usage_data = cast(dict[str, Any], raw_usage) if isinstance(raw_usage, dict) else {}
        usage = OpenAIUsage(
            input_tokens=usage_data.get("prompt_tokens") or usage_data.get("input_tokens") or 0,
            output_tokens=(
                usage_data.get("completion_tokens") or usage_data.get("output_tokens") or 0
            ),
        )
        latency_ms = (time.perf_counter() - started) * 1000
        _emit_audit(
            {
                **audit_record,
                "status": "completed",
                "response_id": body.get("id"),
                "value": value,
                "usage": usage.model_dump(),
                "latency_ms": latency_ms,
            }
        )
        return StructuredGeneration(
            response_id=body.get("id"), value=value, usage=usage, latency_ms=latency_ms
        )


__all__ = [
    "AGNES_MODEL",
    "DEFAULT_AGNES_BASE_URL",
    "AgnesDocumentAdapter",
    "AgnesRequestError",
]
