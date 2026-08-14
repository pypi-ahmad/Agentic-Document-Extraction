"""OpenAI Responses API boundary for grounded document extraction."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger("paperplane.openai_document")

AuditSink = Callable[[dict[str, Any]], None]
_audit_sink: ContextVar[AuditSink | None] = ContextVar("openai_audit_sink", default=None)


@contextmanager
def capture_audit_calls(calls: list[dict[str, Any]]) -> Iterator[None]:
    """Capture sanitized request/response records for the current async context."""
    token = _audit_sink.set(calls.append)
    try:
        yield
    finally:
        _audit_sink.reset(token)


def _emit_audit(record: dict[str, Any]) -> None:
    sink = _audit_sink.get()
    if sink is not None:
        sink(record)


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
        audit_record: dict[str, Any] = {
            "model": model,
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
            _emit_audit(
                {
                    **audit_record,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            logger.warning(
                "OpenAI document request failed for %s: %s",
                model,
                type(exc).__name__,
            )
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
            _emit_audit({**audit_record, "status": "error", "error_type": "refusal"})
            raise OpenAIRequestError("OpenAI refused the structured document request")
        raw = "".join(texts).strip()
        if not raw:
            _emit_audit({**audit_record, "status": "error", "error_type": "empty_output"})
            raise OpenAIRequestError("OpenAI returned no structured output")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            _emit_audit({**audit_record, "status": "error", "error_type": "invalid_json"})
            raise OpenAIRequestError("OpenAI returned invalid structured JSON") from exc
        if not isinstance(value, dict):
            _emit_audit({**audit_record, "status": "error", "error_type": "non_object"})
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
            "OpenAI document request completed: model=%s effort=%s detail=%s "
            "input_tokens=%s output_tokens=%s cached_input_tokens=%s "
            "cache_write_tokens=%s latency_ms=%.1f",
            model,
            reasoning_effort,
            detail,
            usage.input_tokens,
            usage.output_tokens,
            usage.cached_input_tokens,
            usage.cache_write_tokens,
            latency_ms,
        )
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
