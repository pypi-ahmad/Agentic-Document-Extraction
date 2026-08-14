"""Validation and normalization for reusable extraction schemas."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from app.models.schemas import (
    ExtractionSchemaValidationError,
    ExtractionSchemaValidationResponse,
)

MAX_SCHEMA_BYTES = 64 * 1024
MAX_SCHEMA_DEPTH = 8
MAX_SCHEMA_FIELDS = 200
MAX_TABLE_FIELDS = 20
MAX_TABLE_COLUMNS = 100

_SCALAR_TYPES = {"string", "number", "integer", "boolean"}
_TYPES = {*_SCALAR_TYPES, "object", "array"}
_ALLOWED_KEYWORDS = {
    "$schema",
    "$id",
    "title",
    "description",
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "const",
    "format",
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
    "uniqueItems",
    "additionalProperties",
    "x-paperplane-kind",
    "x-paperplane-aliases",
    "x-paperplane-sensitive",
}
_UNSUPPORTED_KEYWORDS = {
    "$ref",
    "$defs",
    "definitions",
    "oneOf",
    "anyOf",
    "allOf",
    "not",
    "if",
    "then",
    "else",
    "patternProperties",
    "dependentSchemas",
    "unevaluatedProperties",
    "contains",
    "prefixItems",
    "pattern",
}


def canonical_schema_bytes(schema: dict[str, Any]) -> bytes:
    return json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def schema_sha256(schema: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_schema_bytes(schema)).hexdigest()


def validate_extraction_schema(schema: dict[str, Any]) -> ExtractionSchemaValidationResponse:
    errors: list[ExtractionSchemaValidationError] = []
    try:
        serialized = canonical_schema_bytes(schema)
    except (TypeError, ValueError):
        return _invalid("/", "invalid_json", "Schema must contain JSON-compatible values")
    if len(serialized) > MAX_SCHEMA_BYTES:
        return _invalid("/", "schema_too_large", f"Schema exceeds {MAX_SCHEMA_BYTES} bytes")

    normalized = copy.deepcopy(schema)
    if normalized.get("type") != "object":
        errors.append(_error("/type", "root_must_be_object", "Root schema type must be object"))
    normalized.setdefault("$schema", "https://json-schema.org/draft/2020-12/schema")
    counts = {"fields": 0, "tables": 0}
    _validate_node(normalized, "", 1, counts, errors)
    if counts["fields"] > MAX_SCHEMA_FIELDS:
        errors.append(
            _error("/properties", "too_many_fields", f"Schema exceeds {MAX_SCHEMA_FIELDS} fields")
        )
    if counts["tables"] > MAX_TABLE_FIELDS:
        errors.append(
            _error("/properties", "too_many_tables", f"Schema exceeds {MAX_TABLE_FIELDS} tables")
        )
    if not errors:
        try:
            Draft202012Validator.check_schema(normalized)
        except SchemaError as exc:
            path = _pointer(exc.absolute_schema_path)
            errors.append(_error(path, "invalid_json_schema", exc.message))
    return ExtractionSchemaValidationResponse(
        valid=not errors,
        normalized_schema=normalized if not errors else None,
        errors=errors,
    )


def _validate_node(
    node: Any,
    path: str,
    depth: int,
    counts: dict[str, int],
    errors: list[ExtractionSchemaValidationError],
) -> None:
    pointer = path or "/"
    if depth > MAX_SCHEMA_DEPTH:
        errors.append(
            _error(pointer, "schema_too_deep", f"Schema exceeds depth {MAX_SCHEMA_DEPTH}")
        )
        return
    if not isinstance(node, dict):
        errors.append(_error(pointer, "invalid_schema_node", "Every schema node must be an object"))
        return
    for keyword in node:
        keyword_path = f"{path}/{_escape(keyword)}" or "/"
        if keyword in _UNSUPPORTED_KEYWORDS or keyword not in _ALLOWED_KEYWORDS:
            errors.append(
                _error(keyword_path, "unsupported_keyword", f"Keyword {keyword} is not supported")
            )

    node_type = node.get("type")
    if node_type not in _TYPES:
        errors.append(
            _error(f"{path}/type", "unsupported_type", "Type must be object, array, or a scalar")
        )
        return
    aliases = node.get("x-paperplane-aliases")
    if aliases is not None and (
        not isinstance(aliases, list)
        or not all(isinstance(alias, str) and alias.strip() for alias in aliases)
    ):
        errors.append(
            _error(
                f"{path}/x-paperplane-aliases",
                "invalid_aliases",
                "Aliases must be a list of non-empty strings",
            )
        )

    if node_type == "object":
        properties = node.get("properties", {})
        if not isinstance(properties, dict):
            errors.append(
                _error(f"{path}/properties", "invalid_properties", "Properties must be an object")
            )
            return
        node["additionalProperties"] = False
        required = node.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            errors.append(
                _error(f"{path}/required", "invalid_required", "Required must be a string list")
            )
        elif any(item not in properties for item in required):
            errors.append(
                _error(
                    f"{path}/required",
                    "unknown_required_field",
                    "Every required field must exist in properties",
                )
            )
        for name, child in properties.items():
            counts["fields"] += 1
            if (
                not isinstance(name, str)
                or not name.strip()
                or any(ord(char) < 32 for char in name)
            ):
                errors.append(
                    _error(
                        f"{path}/properties", "invalid_field_name", "Field names must be printable"
                    )
                )
                continue
            _validate_node(
                child,
                f"{path}/properties/{_escape(name)}",
                depth + 1,
                counts,
                errors,
            )
        return

    if node_type == "array":
        items = node.get("items")
        if not isinstance(items, dict):
            errors.append(
                _error(f"{path}/items", "invalid_items", "Arrays require one item schema")
            )
            return
        if node.get("x-paperplane-kind") == "table":
            counts["tables"] += 1
            properties = items.get("properties") if items.get("type") == "object" else None
            if not isinstance(properties, dict):
                errors.append(
                    _error(
                        f"{path}/x-paperplane-kind",
                        "invalid_table_schema",
                        "Tables must be arrays of objects",
                    )
                )
            elif len(properties) > MAX_TABLE_COLUMNS:
                errors.append(
                    _error(
                        f"{path}/items/properties",
                        "too_many_table_columns",
                        f"A table cannot exceed {MAX_TABLE_COLUMNS} columns",
                    )
                )
            elif any(
                not isinstance(value, dict) or value.get("type") not in _SCALAR_TYPES
                for value in properties.values()
            ):
                errors.append(
                    _error(
                        f"{path}/items/properties",
                        "invalid_table_schema",
                        "Table columns must use scalar types",
                    )
                )
        _validate_node(items, f"{path}/items", depth + 1, counts, errors)


def _pointer(parts: Any) -> str:
    values = [str(part) for part in parts]
    return "/" + "/".join(_escape(value) for value in values) if values else "/"


def _escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _error(path: str, code: str, message: str) -> ExtractionSchemaValidationError:
    return ExtractionSchemaValidationError(path=path or "/", code=code, message=message[:500])


def _invalid(path: str, code: str, message: str) -> ExtractionSchemaValidationResponse:
    return ExtractionSchemaValidationResponse(valid=False, errors=[_error(path, code, message)])
