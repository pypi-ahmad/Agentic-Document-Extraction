"""Robust parser for LLM extraction output.

LLMs frequently return JSON wrapped in markdown fences, with preamble
text, trailing commas, or values that don't match the requested types.
This module provides:

- ``parse_llm_json``: extracts valid JSON from messy LLM output
- ``coerce_to_schema``: coerces extracted values to match schema field types
"""

from __future__ import annotations

import json
import re
from typing import Any

# ── JSON extraction ──────────────────────────────────────────────────

# Matches ```json ... ``` or ``` ... ``` fenced blocks (DOTALL so . matches newlines)
_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)

# Trailing commas before } or ]
_TRAILING_COMMA_RE = re.compile(r",\s*([\]}])")


def _try_parse_obj(text: str) -> dict[str, Any] | None:
    """Parse a string, return the first dict (or None)."""
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict):
        return obj
    return None


def parse_llm_json(raw: str) -> dict[str, Any]:
    """Parse a JSON object from raw LLM output.

    Handles common LLM output quirks:
    1. Markdown fenced code blocks (```json ... ```)
    2. Preamble/postamble text around the JSON object
    3. Trailing commas in objects/arrays
    4. Nested JSON within conversational text

    Returns
    -------
    dict
        The parsed JSON object.

    Raises
    ------
    ValueError
        If no valid JSON object can be extracted.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty LLM response")

    # Strategy 1: Direct parse (fast path for well-behaved models)
    stripped = raw.strip()
    obj = _try_parse(stripped)
    if isinstance(obj, dict):
        return obj

    # Strategy 2: Extract from markdown fences
    for match in _FENCED_JSON_RE.finditer(raw):
        obj = _try_parse(match.group(1).strip())
        if isinstance(obj, dict):
            return obj

    # Strategy 3: Find the outermost { ... } span
    obj = _try_brace_extraction(raw)
    if isinstance(obj, dict):
        return obj

    raise ValueError(
        f"Could not extract a JSON object from LLM response "
        f"(length={len(raw)}, preview={raw[:120]!r})"
    )


def _try_parse(text: str) -> Any:
    """Try json.loads; on failure try fixing trailing commas."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    cleaned = _TRAILING_COMMA_RE.sub(r"\1", text)
    if cleaned != text:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    return None


def _try_brace_extraction(text: str) -> Any:
    """Find balanced { ... } substrings and parse the first valid JSON object.

    Tries every top-level ``{`` in the text so that preamble containing
    curly braces (e.g. ``{invalid}``) doesn't shadow the real payload.
    """
    pos = 0
    while True:
        start = text.find("{", pos)
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape = False
        end = -1

        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1:
            return None

        candidate = text[start : end + 1]
        result = _try_parse(candidate)
        if isinstance(result, dict):
            return result

        # This { ... } wasn't valid JSON; try the next one
        pos = start + 1


# ── Schema-aware coercion ────────────────────────────────────────────


def coerce_to_schema(
    data: dict[str, Any],
    schema_fields: list[dict],
) -> dict[str, Any]:
    """Coerce extracted values to match the declared schema field types.

    Performs best-effort type coercion so that values returned as the
    wrong type by the LLM (e.g. ``"42"`` for a number field, ``"true"``
    for a boolean) are silently fixed rather than causing validation
    failures.

    Unknown fields (not in the schema) are dropped so the workflow result
    stays aligned to the declared extraction schema.
    Coercion that fails is a no-op: the original value is kept so
    downstream validation can flag it.
    """
    type_map = {f["name"]: f.get("field_type", "string") for f in schema_fields}
    result: dict[str, Any] = {}

    for key, value in data.items():
        field_type = type_map.get(key)
        if field_type is None:
            continue
        if value is not None:
            result[key] = _coerce_value(value, field_type)
        else:
            result[key] = value

    return result


def _coerce_value(value: Any, field_type: str) -> Any:
    """Attempt to coerce a single value to the declared type."""
    try:
        if field_type == "number":
            return _coerce_number(value)
        if field_type == "boolean":
            return _coerce_boolean(value)
        if field_type == "string":
            return _coerce_string(value)
        if field_type == "date":
            return _coerce_date(value)
        if field_type == "list":
            return _coerce_list(value)
        if field_type == "object":
            return _coerce_object(value)
    except (ValueError, TypeError):
        pass
    return value


def _coerce_number(value: Any) -> int | float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace(" ", "")
        if not cleaned:
            raise ValueError("empty string")
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    raise ValueError(f"Cannot coerce {type(value).__name__} to number")


def _coerce_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in {"true", "yes", "1"}:
            return True
        if lower in {"false", "no", "0"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"Cannot coerce {type(value).__name__} to boolean")


def _coerce_string(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    raise ValueError(f"Cannot coerce {type(value).__name__} to string")


def _coerce_date(value: Any) -> str:
    """Normalize date strings to ISO 8601 (YYYY-MM-DD)."""
    if not isinstance(value, str):
        raise ValueError(f"Cannot coerce {type(value).__name__} to date")
    stripped = value.strip()
    # Already ISO 8601 date or datetime
    if re.match(r"^\d{4}-\d{2}-\d{2}", stripped):
        return stripped[:10]
    # US format: MM/DD/YYYY or M/D/YYYY
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", stripped)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return stripped


def _coerce_list(value: Any) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in value.split(",") if item.strip()]
    raise ValueError(f"Cannot coerce {type(value).__name__} to list")


def _coerce_object(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("{"):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Cannot coerce {type(value).__name__} to object")


# ── Confidence extraction ────────────────────────────────────────────


def extract_confidence(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
    """Split the ``_confidence`` map out of LLM-returned data.

    Returns a ``(clean_data, confidence)`` tuple.  ``confidence`` maps
    field names to 0.0-1.0 scores.  If the model didn't return a
    ``_confidence`` key the map is empty.  Invalid entries are silently
    dropped.
    """
    confidence_raw = data.pop("_confidence", None)
    clean_data = {k: v for k, v in data.items() if k != "_confidence"}

    confidence: dict[str, float] = {}
    if isinstance(confidence_raw, dict):
        for k, v in confidence_raw.items():
            try:
                score = float(v)
                if 0.0 <= score <= 1.0:
                    confidence[k] = round(score, 3)
            except (ValueError, TypeError):
                pass

    return clean_data, confidence
