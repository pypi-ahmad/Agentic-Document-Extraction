"""Anthropic Messages API boundary for grounded document extraction."""

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

logger = logging.getLogger("paperplane.anthropic_document")

ANTHROPIC_MODEL = "claude-sonnet-5"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


class AnthropicRequestError(OpenAIRequestError):
    """Raised when Claude cannot return a structured document result."""


class AnthropicDocumentAdapter:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = DEFAULT_ANTHROPIC_BASE_URL,
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
        if model != ANTHROPIC_MODEL:
            raise AnthropicRequestError(f"Unsupported Anthropic model: {model}")
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
            raise AnthropicRequestError("Anthropic API key is not configured")

        content: list[dict[str, Any]] = []
        if image is not None:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.b64encode(image).decode("ascii"),
                    },
                }
            )
        prompt = (
            instructions if context is None else f"{instructions}\n\nDocument context:\n{context}"
        )
        content.append({"type": "text", "text": prompt})
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": 16_384,
            "messages": [{"role": "user", "content": content}],
            "output_config": output_config,
            "thinking": {"type": "disabled" if reasoning_effort == "none" else "adaptive"},
        }
        if reasoning_effort != "none":
            output_config["effort"] = reasoning_effort

        started = time.perf_counter()
        try:
            response = await self.http.post(
                f"{self.base_url}/v1/messages",
                headers={
                    "anthropic-version": "2023-06-01",
                    "x-api-key": self.api_key,
                },
                json=payload,
            )
            response.raise_for_status()
            body = cast(dict[str, Any], response.json())
            stop_reason = body.get("stop_reason")
            if stop_reason == "refusal":
                raise AnthropicRequestError("Anthropic refused the structured document request")
            if stop_reason in {"max_tokens", "model_context_window_exceeded"}:
                raise AnthropicRequestError("Anthropic returned truncated structured output")
            response_content = cast(list[dict[str, Any]], body["content"])
            raw = "".join(
                str(block.get("text", ""))
                for block in response_content
                if block.get("type") == "text"
            ).strip()
            value_data: Any = json.loads(raw)
        except AnthropicRequestError:
            raise
        except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            _emit_audit(
                {
                    **audit_record,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            logger.warning("Anthropic document request failed: %s", type(exc).__name__)
            raise AnthropicRequestError("Anthropic document request failed") from exc
        if not isinstance(value_data, dict):
            _emit_audit({**audit_record, "status": "error", "error_type": "non_object"})
            raise AnthropicRequestError("Anthropic structured output must be a JSON object")
        value = cast(dict[str, Any], value_data)

        raw_usage = body.get("usage")
        usage_data = cast(dict[str, Any], raw_usage) if isinstance(raw_usage, dict) else {}
        usage = OpenAIUsage(
            input_tokens=usage_data.get("input_tokens") or 0,
            output_tokens=usage_data.get("output_tokens") or 0,
            cached_input_tokens=usage_data.get("cache_read_input_tokens") or 0,
            cache_write_tokens=usage_data.get("cache_creation_input_tokens") or 0,
        )
        latency_ms = (time.perf_counter() - started) * 1000
        response_id = str(body["id"]) if body.get("id") else None
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
    "ANTHROPIC_MODEL",
    "DEFAULT_ANTHROPIC_BASE_URL",
    "AnthropicDocumentAdapter",
    "AnthropicRequestError",
]
