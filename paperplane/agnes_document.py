"""Agnes Chat Completions boundary for grounded document extraction."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from typing import Any, Literal, cast

import httpx
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from paperplane.openai_document import (
    OpenAIRequestError,
    OpenAIUsage,
    StructuredGeneration,
    _emit_audit,
)

logger = logging.getLogger("paperplane.agnes_document")

AGNES_MODEL = "agnes-2.5-flash"
DEFAULT_AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
_MAX_STRUCTURED_ATTEMPTS = 2


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


def _structured_value(body: dict[str, Any], schema_name: str) -> dict[str, Any]:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ValueError("Agnes response did not contain a message")
    choice = cast(dict[str, Any], choices[0])
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("Agnes response did not contain a message")
    message_data = cast(dict[str, Any], message)
    tool_calls = message_data.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        if not isinstance(tool_calls[0], dict):
            raise ValueError("Agnes returned an invalid tool call")
        tool_call = cast(dict[str, Any], tool_calls[0])
        function = tool_call.get("function")
        if not isinstance(function, dict):
            raise ValueError("Agnes returned an unexpected tool call")
        function_data = cast(dict[str, Any], function)
        if function_data.get("name") != schema_name:
            raise ValueError("Agnes returned an unexpected tool call")
        arguments = function_data.get("arguments")
        value_data: Any = json.loads(arguments) if isinstance(arguments, str) else arguments
    else:
        content = message_data.get("content")
        if not isinstance(content, str):
            raise ValueError("Agnes returned neither tool arguments nor JSON content")
        value_data = json.loads(_json_text(content))
    if not isinstance(value_data, dict):
        raise ValueError("Agnes structured output must be a JSON object")
    return cast(dict[str, Any], value_data)


def _geometry_error(value: Any, path: str = "$") -> str | None:
    if isinstance(value, dict):
        value_data = cast(dict[str, Any], value)
        coordinate_names = {"left", "top", "right", "bottom"}
        if coordinate_names.issubset(value_data):
            left, top, right, bottom = (
                value_data["left"],
                value_data["top"],
                value_data["right"],
                value_data["bottom"],
            )
            if all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in (left, top, right, bottom)
            ) and (left >= right or top >= bottom):
                return f"{path} must have left < right and top < bottom"
        for key, child in value_data.items():
            if error := _geometry_error(child, f"{path}.{key}"):
                return error
    elif isinstance(value, list):
        for index, child in enumerate(cast(list[Any], value)):
            if error := _geometry_error(child, f"{path}[{index}]"):
                return error
    return None


def _normalize_agnes_value(value: dict[str, Any]) -> dict[str, Any]:
    """Normalize Agnes JSON equivalents that the pipeline already accepts."""

    def normalize_boxes(item: Any) -> None:
        if isinstance(item, dict):
            item_data = cast(dict[str, Any], item)
            coordinate_names = ("left", "top", "right", "bottom")
            coordinates = [item_data.get(name) for name in coordinate_names]
            if (
                all(
                    isinstance(coordinate, (int, float)) and not isinstance(coordinate, bool)
                    for coordinate in coordinates
                )
                and any(cast(float, coordinate) > 1 for coordinate in coordinates)
                and all(0 <= cast(float, coordinate) <= 1000 for coordinate in coordinates)
            ):
                for name in coordinate_names:
                    item_data[name] = cast(float, item_data[name]) / 1000
            for child in item_data.values():
                normalize_boxes(child)
        elif isinstance(item, list):
            for child in cast(list[Any], item):
                normalize_boxes(child)

    chunks = value.get("chunks")
    if isinstance(chunks, list):
        for raw_chunk in chunks:
            if not isinstance(raw_chunk, dict):
                continue
            chunk = cast(dict[str, Any], raw_chunk)
            chunk.setdefault("markdown", str(chunk.get("text", "")))
            chunk.setdefault("parent_order", None)
            chunk.setdefault("atomic_lines", [])
            for name in ("row", "col", "rowspan", "colspan"):
                chunk.setdefault(name, None)
    normalize_boxes(value)
    return value


def _validate_structured_value(value: dict[str, Any], schema: dict[str, Any]) -> None:
    Draft202012Validator(schema).validate(value)
    if error := _geometry_error(value):
        raise ValueError(error)


def _usage(body: dict[str, Any]) -> OpenAIUsage:
    raw_usage = body.get("usage")
    usage_data = cast(dict[str, Any], raw_usage) if isinstance(raw_usage, dict) else {}
    return OpenAIUsage(
        input_tokens=usage_data.get("prompt_tokens") or usage_data.get("input_tokens") or 0,
        output_tokens=usage_data.get("completion_tokens") or usage_data.get("output_tokens") or 0,
    )


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
        prompt_parts = [instructions, f"Call the {schema_name} function with the complete result."]
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
        started = time.perf_counter()
        total_usage = OpenAIUsage()
        validation_feedback: str | None = None
        for attempt in range(1, _MAX_STRUCTURED_ATTEMPTS + 1):
            request_content = list(content)
            if validation_feedback is not None:
                request_content.append(
                    {
                        "type": "text",
                        "text": (
                            "Previous structured response was invalid: "
                            f"{validation_feedback}. Return corrected function arguments."
                        ),
                    }
                )
            payload: dict[str, Any] = {
                "model": AGNES_MODEL,
                "messages": [{"role": "user", "content": request_content}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": schema_name,
                            "description": "Return the requested structured document result.",
                            "parameters": schema,
                        },
                    }
                ],
                "tool_choice": {"type": "function", "function": {"name": schema_name}},
                "temperature": 0,
                "max_tokens": 16_384,
                "stream": False,
            }
            try:
                response = await self.http.post(
                    _chat_completions_url(self.base_url),
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                body_data: Any = response.json()
                if not isinstance(body_data, dict):
                    raise TypeError("Agnes response must be a JSON object")
                body = cast(dict[str, Any], body_data)
            except (httpx.HTTPError, ValueError, TypeError) as exc:
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

            attempt_usage = _usage(body)
            total_usage.input_tokens += attempt_usage.input_tokens
            total_usage.output_tokens += attempt_usage.output_tokens
            try:
                value = _normalize_agnes_value(_structured_value(body, schema_name))
                _validate_structured_value(value, schema)
            except (KeyError, IndexError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                validation_feedback = str(exc).splitlines()[0]
                if attempt < _MAX_STRUCTURED_ATTEMPTS:
                    continue
                latency_ms = (time.perf_counter() - started) * 1000
                _emit_audit(
                    {
                        **audit_record,
                        "status": "error",
                        "error_type": "invalid_structured_output",
                        "attempts": attempt,
                        "usage": total_usage.model_dump(),
                        "latency_ms": latency_ms,
                    }
                )
                logger.warning(
                    "Agnes returned invalid structured output after %d attempts: %s",
                    attempt,
                    validation_feedback,
                )
                raise AgnesRequestError(
                    "Agnes did not return valid structured output after two attempts"
                ) from exc

            latency_ms = (time.perf_counter() - started) * 1000
            _emit_audit(
                {
                    **audit_record,
                    "status": "completed",
                    "response_id": body.get("id"),
                    "value": value,
                    "attempts": attempt,
                    "usage": total_usage.model_dump(),
                    "latency_ms": latency_ms,
                }
            )
            return StructuredGeneration(
                response_id=body.get("id"),
                value=value,
                usage=total_usage,
                latency_ms=latency_ms,
            )

        raise AssertionError("structured attempt loop exhausted")


__all__ = [
    "AGNES_MODEL",
    "DEFAULT_AGNES_BASE_URL",
    "AgnesDocumentAdapter",
    "AgnesRequestError",
]
