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
from typing import Any, Literal, cast

import httpx
from pydantic import BaseModel, Field

from paperplane.prompt_loader import load_prompt

logger = logging.getLogger("paperplane.openai_document")

AuditSink = Callable[[dict[str, Any]], None]
# ContextVar isolates the audit sink per async task, not per thread, so concurrent
# document parses running in the same event loop each capture their own calls.
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
    def __init__(self, message: str, *, usage: OpenAIUsage | None = None) -> None:
        super().__init__(message)
        self.usage = usage or OpenAIUsage()


class OpenAIUsage(BaseModel):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)


class StructuredGeneration(BaseModel):
    response_id: str | None = None
    value: dict[str, Any]
    usage: OpenAIUsage
    model_usage: dict[str, OpenAIUsage] = Field(default_factory=dict)
    latency_ms: float = Field(ge=0)
    presegmented: bool = False
    warnings: list[str] = Field(default_factory=list)


def _responses_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    return f"{normalized}/responses" if normalized.endswith("/v1") else f"{normalized}/v1/responses"


def _usage_from_body(body: dict[str, Any]) -> OpenAIUsage:
    raw_usage = body.get("usage")
    usage_data = cast(dict[str, Any], raw_usage) if isinstance(raw_usage, dict) else {}
    raw_details = usage_data.get("input_tokens_details")
    input_details = cast(dict[str, Any], raw_details) if isinstance(raw_details, dict) else {}
    return OpenAIUsage(
        input_tokens=usage_data.get("input_tokens") or 0,
        output_tokens=usage_data.get("output_tokens") or 0,
        cached_input_tokens=input_details.get("cached_tokens") or 0,
        cache_write_tokens=input_details.get("cache_write_tokens") or 0,
    )


def _add_usage(left: OpenAIUsage, right: OpenAIUsage) -> OpenAIUsage:
    return OpenAIUsage(
        input_tokens=left.input_tokens + right.input_tokens,
        output_tokens=left.output_tokens + right.output_tokens,
        cached_input_tokens=left.cached_input_tokens + right.cached_input_tokens,
        cache_write_tokens=left.cache_write_tokens + right.cache_write_tokens,
    )


def _incomplete_reason(body: dict[str, Any]) -> str | None:
    details = body.get("incomplete_details")
    if not isinstance(details, dict):
        return None
    reason = cast(dict[str, Any], details).get("reason")
    return str(reason) if reason is not None else None


class OpenAIDocumentAdapter:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com",
        provider_name: str = "OpenAI",
        explicit_prompt_cache: bool = True,
        image_detail: bool = True,
        minimum_reasoning_effort: Literal["none", "low"] = "none",
    ) -> None:
        self.http = http
        self.api_key = api_key
        self.base_url = base_url
        self.provider_name = provider_name
        self.explicit_prompt_cache = explicit_prompt_cache
        self.image_detail = image_detail
        self.minimum_reasoning_effort = minimum_reasoning_effort

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
        if model == "gpt-6-sol":
            reasoning_effort = "medium"
        audit_record: dict[str, Any] = {
            "model": model,
            "provider": self.provider_name,
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
            raise OpenAIRequestError(f"{self.provider_name} API key is not configured")
        encoded = base64.b64encode(image).decode("ascii") if image is not None else None
        content: list[dict[str, Any]] = [
            {
                "type": "input_text",
                "text": instructions,
                "prompt_cache_breakpoint": {"mode": "explicit"},
            }
        ]
        if encoded is not None:
            image_content: dict[str, Any] = {
                "type": "input_image",
                "image_url": f"data:image/png;base64,{encoded}",
            }
            if self.image_detail:
                image_content["detail"] = detail
            content.append(image_content)
        if context is not None:
            content.append({"type": "input_text", "text": context})
        effective_effort = (
            "low"
            if reasoning_effort == "none" and self.minimum_reasoning_effort == "low"
            else reasoning_effort
        )
        payload: dict[str, Any] = {
            "model": model,
            "store": False,
            "reasoning": {"effort": effective_effort},
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
        # xAI does not support explicit prompt caching; explicit_prompt_cache=False strips
        # the cache fields so the request is accepted by the xAI Responses endpoint.
        if self.explicit_prompt_cache:
            payload["prompt_cache_key"] = prompt_cache_key
            payload["prompt_cache_options"] = {"mode": "explicit", "ttl": "30m"}
        else:
            content[0].pop("prompt_cache_breakpoint", None)
        started = time.perf_counter()
        retry_usage = OpenAIUsage()
        content_filter_retry = False
        first_response_id: str | None = None
        try:

            async def request(request_payload: dict[str, Any]) -> dict[str, Any]:
                response = await self.http.post(
                    _responses_url(self.base_url),
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=request_payload,
                )
                response.raise_for_status()
                raw_result = response.json()
                if not isinstance(raw_result, dict):
                    raise TypeError("Responses API body must be an object")
                return cast(dict[str, Any], raw_result)

            body = await request(payload)
            incomplete_reason = _incomplete_reason(body)
            if (
                model == "gpt-6-sol"
                and self.provider_name == "OpenAI"
                and body.get("status") == "incomplete"
                and incomplete_reason == "content_filter"
            ):
                content_filter_retry = True
                first_response_id = body.get("id")
                retry_usage = _usage_from_body(body)
                retry_payload = json.loads(json.dumps(payload))
                retry_payload["input"][0]["content"][0]["text"] = load_prompt(
                    "content-filter-retry.md"
                )
                body = await request(retry_payload)
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
                "%s document request failed for %s: %s",
                self.provider_name,
                model,
                type(exc).__name__,
            )
            raise OpenAIRequestError(f"{self.provider_name} document request failed") from exc

        incomplete_reason = _incomplete_reason(body)
        if body.get("status") == "incomplete":
            error_type = f"incomplete_{incomplete_reason or 'unknown'}"
            _emit_audit(
                {
                    **audit_record,
                    "status": "error",
                    "error_type": error_type,
                    "content_filter_retry": content_filter_retry,
                    "response_id": body.get("id"),
                }
            )
            if incomplete_reason == "content_filter":
                raise OpenAIRequestError(
                    f"{self.provider_name} content filter interrupted structured output",
                    usage=_add_usage(retry_usage, _usage_from_body(body)),
                )
            raise OpenAIRequestError(f"{self.provider_name} returned incomplete structured output")

        texts: list[str] = []
        refused = False
        raw_outputs = body.get("output")
        outputs = cast(list[Any], raw_outputs) if isinstance(raw_outputs, list) else []
        for output in outputs:
            if not isinstance(output, dict):
                continue
            output_body = cast(dict[str, Any], output)
            raw_content = output_body.get("content")
            content_items = cast(list[Any], raw_content) if isinstance(raw_content, list) else []
            for item in content_items:
                if not isinstance(item, dict):
                    continue
                response_item = cast(dict[str, Any], item)
                if response_item.get("type") == "output_text":
                    texts.append(str(response_item.get("text", "")))
                elif response_item.get("type") == "refusal":
                    refused = True
        if refused:
            _emit_audit({**audit_record, "status": "error", "error_type": "refusal"})
            raise OpenAIRequestError(
                f"{self.provider_name} refused the structured document request"
            )
        raw = "".join(texts).strip()
        if not raw:
            _emit_audit({**audit_record, "status": "error", "error_type": "empty_output"})
            raise OpenAIRequestError(f"{self.provider_name} returned no structured output")
        try:
            value = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            _emit_audit({**audit_record, "status": "error", "error_type": "invalid_json"})
            raise OpenAIRequestError(
                f"{self.provider_name} returned invalid structured JSON"
            ) from exc
        if not isinstance(value, dict):
            _emit_audit({**audit_record, "status": "error", "error_type": "non_object"})
            raise OpenAIRequestError(
                f"{self.provider_name} structured output must be a JSON object"
            )
        value = cast(dict[str, Any], value)

        usage = _add_usage(retry_usage, _usage_from_body(body))
        warnings = ["content_filter_retry_used"] if content_filter_retry else []
        latency_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s document request completed: model=%s effort=%s detail=%s "
            "input_tokens=%s output_tokens=%s cached_input_tokens=%s "
            "cache_write_tokens=%s latency_ms=%.1f",
            self.provider_name,
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
                "first_response_id": first_response_id,
                "content_filter_retry": content_filter_retry,
                "value": value,
                "usage": usage.model_dump(),
                "latency_ms": latency_ms,
            }
        )
        return StructuredGeneration(
            response_id=body.get("id"),
            value=value,
            usage=usage,
            latency_ms=latency_ms,
            warnings=warnings,
        )
