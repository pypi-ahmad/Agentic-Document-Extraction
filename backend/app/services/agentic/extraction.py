"""Deterministic validation and grounding around the Terra schema-extraction call."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator, SchemaError


class ExtractionServiceError(ValueError):
    """Base error that API adapters can turn into a safe client response."""

    status_code = 422


class InvalidExtractionSchemaError(ExtractionServiceError):
    """The requested JSON Schema is outside the supported DPT-style subset."""


class StrictSchemaViolationError(ExtractionServiceError):
    """A model candidate violates a schema requested with ``strict=True``."""


class InvalidGroundingEvidenceError(ExtractionServiceError):
    """Provider evidence does not point to the supplied Markdown exactly."""


@dataclass(frozen=True)
class SourceEvidence:
    """A provider-supplied Markdown substring or half-open Unicode code-point range."""

    text: str | None = None
    start: int | None = None
    end: int | None = None


@dataclass(frozen=True)
class ExtractionCandidate:
    """Structured Terra output; evidence is keyed by RFC 6901-style leaf paths."""

    value: Any
    evidence: Mapping[str, Sequence[SourceEvidence]] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionRequest:
    markdown: str
    schema: dict[str, Any]


@dataclass(frozen=True)
class ExtractionResult:
    extraction: Any
    extraction_metadata: Any
    warnings: list[str]
    schema_violation_error: str | None
    agent_summary: dict[str, str]


TerraExtractor = Callable[[ExtractionRequest], Awaitable[ExtractionCandidate]]

_ALLOWED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "description",
        "format",
        "x-alternativeNames",
        "additionalProperties",
    }
)
_PRIMITIVE_TYPES = frozenset({"string", "number", "integer", "boolean", "null"})


class AgenticSchemaExtractor:
    """Run one injected Terra extraction call, then deterministically validate and ground it."""

    def __init__(self, terra_extractor: TerraExtractor) -> None:
        self._terra_extractor = terra_extractor

    async def extract(
        self,
        *,
        markdown: str,
        schema: dict[str, Any],
        strict: bool = False,
    ) -> ExtractionResult:
        validate_extraction_schema(schema)
        candidate = await self._terra_extractor(ExtractionRequest(markdown=markdown, schema=schema))
        if not isinstance(candidate, ExtractionCandidate):
            raise TypeError("Terra extractor must return ExtractionCandidate")

        violations = sorted(
            Draft202012Validator(schema).iter_errors(candidate.value),
            key=lambda error: list(error.absolute_path),
        )
        violation_message = _format_schema_violations(violations)
        if violation_message and strict:
            raise StrictSchemaViolationError(violation_message)

        metadata = _build_metadata(candidate.value, candidate.evidence, markdown)
        return ExtractionResult(
            extraction=candidate.value,
            extraction_metadata=metadata,
            warnings=["schema_validation_failed"] if violation_message else [],
            schema_violation_error=violation_message,
            agent_summary={
                "agent": "terra_schema_extractor",
                "model": "gpt-5.6-terra",
                "status": "completed",
            },
        )


def validate_extraction_schema(schema: dict[str, Any]) -> None:
    """Validate the deliberately small extraction-schema contract before model invocation."""

    if not isinstance(schema, dict):
        raise InvalidExtractionSchemaError("schema must be a JSON object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise InvalidExtractionSchemaError(f"invalid JSON Schema: {error.message}") from error
    _validate_schema_node(schema, path="$")


def _validate_schema_node(node: Any, *, path: str) -> None:
    if not isinstance(node, dict):
        raise InvalidExtractionSchemaError(f"{path} must be an object")
    unsupported = sorted(set(node) - _ALLOWED_KEYWORDS)
    if unsupported:
        raise InvalidExtractionSchemaError(
            f"{path} uses unsupported schema keyword(s): {', '.join(unsupported)}"
        )

    node_type = node.get("type")
    if not isinstance(node_type, str) or node_type not in {"object", "array", *_PRIMITIVE_TYPES}:
        raise InvalidExtractionSchemaError(f"{path}.type must be a supported single JSON type")
    if "description" in node and not isinstance(node["description"], str):
        raise InvalidExtractionSchemaError(f"{path}.description must be a string")
    if "format" in node and not isinstance(node["format"], str):
        raise InvalidExtractionSchemaError(f"{path}.format must be a string")
    aliases = node.get("x-alternativeNames")
    if aliases is not None and (
        not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases)
    ):
        raise InvalidExtractionSchemaError(f"{path}.x-alternativeNames must be a list of strings")

    if node_type == "object":
        _validate_object_schema(node, path=path)
        return
    if node_type == "array":
        _validate_array_schema(node, path=path)
        return
    _validate_primitive_schema(node, node_type=node_type, path=path)


def _validate_object_schema(node: dict[str, Any], *, path: str) -> None:
    forbidden = {"items", "enum"}.intersection(node)
    if forbidden:
        raise InvalidExtractionSchemaError(
            f"{path} object schema cannot use {', '.join(sorted(forbidden))}"
        )
    properties = node.get("properties", {})
    if not isinstance(properties, dict) or not all(isinstance(name, str) for name in properties):
        raise InvalidExtractionSchemaError(f"{path}.properties must be an object")
    required = node.get("required", [])
    if not isinstance(required, list) or not all(isinstance(name, str) for name in required):
        raise InvalidExtractionSchemaError(f"{path}.required must be a list of strings")
    if not set(required).issubset(properties):
        raise InvalidExtractionSchemaError(f"{path}.required names must exist in properties")
    additional = node.get("additionalProperties")
    if additional is not None and not isinstance(additional, bool):
        raise InvalidExtractionSchemaError(f"{path}.additionalProperties must be boolean")
    for name, child in properties.items():
        _validate_schema_node(child, path=f"{path}.properties.{name}")


def _validate_array_schema(node: dict[str, Any], *, path: str) -> None:
    forbidden = {"properties", "required", "enum", "additionalProperties"}.intersection(node)
    if forbidden:
        raise InvalidExtractionSchemaError(
            f"{path} array schema cannot use {', '.join(sorted(forbidden))}"
        )
    if not isinstance(node.get("items"), dict):
        raise InvalidExtractionSchemaError(f"{path}.items must be an object schema")
    _validate_schema_node(node["items"], path=f"{path}.items")


def _validate_primitive_schema(node: dict[str, Any], *, node_type: str, path: str) -> None:
    forbidden = {"properties", "required", "items", "additionalProperties"}.intersection(node)
    if forbidden:
        raise InvalidExtractionSchemaError(
            f"{path} primitive schema cannot use {', '.join(sorted(forbidden))}"
        )
    if "enum" in node and (
        node_type != "string"
        or not isinstance(node["enum"], list)
        or not all(isinstance(value, str) for value in node["enum"])
    ):
        raise InvalidExtractionSchemaError(f"{path}.enum is supported only for string values")


def _format_schema_violations(violations: Sequence[Any]) -> str | None:
    if not violations:
        return None
    return "; ".join(
        f"{'/' + '/'.join(str(part) for part in error.absolute_path) or '/'}: {error.message}"
        for error in violations
    )


def _build_metadata(
    value: Any, evidence: Mapping[str, Sequence[SourceEvidence]], markdown: str
) -> Any:
    def walk(item: Any, path: str) -> Any:
        if isinstance(item, dict):
            return {key: walk(child, _join_pointer(path, key)) for key, child in item.items()}
        if isinstance(item, list):
            return [
                walk(child, _join_pointer(path, str(index))) for index, child in enumerate(item)
            ]
        ranges = _ranges_for_leaf(item, evidence.get(path, ()), markdown)
        return {"value": item, "ranges": ranges}

    return walk(value, "")


def _join_pointer(base: str, segment: str) -> str:
    escaped = segment.replace("~", "~0").replace("/", "~1")
    return f"{base}/{escaped}"


def _ranges_for_leaf(
    value: Any, evidence: Sequence[SourceEvidence], markdown: str
) -> list[dict[str, int]]:
    entries = list(evidence) if evidence else _fallback_evidence(value)
    ranges = [_resolve_evidence(item, markdown) for item in entries]
    unique = sorted(set(ranges))
    return [{"start": start, "end": end} for start, end in unique]


def _fallback_evidence(value: Any) -> list[SourceEvidence]:
    if value is None:
        return []
    if isinstance(value, bool):
        return [SourceEvidence(text=str(value).lower())]
    if isinstance(value, (str, int, float)):
        return [SourceEvidence(text=str(value))]
    return []


def _resolve_evidence(evidence: SourceEvidence, markdown: str) -> tuple[int, int]:
    if (evidence.start is None) != (evidence.end is None):
        raise InvalidGroundingEvidenceError("evidence start and end must be supplied together")
    if evidence.start is not None and evidence.end is not None:
        if evidence.start < 0 or evidence.end < evidence.start or evidence.end > len(markdown):
            raise InvalidGroundingEvidenceError("evidence range is outside Markdown")
        if evidence.text is not None and markdown[evidence.start : evidence.end] != evidence.text:
            raise InvalidGroundingEvidenceError("evidence text does not match its Markdown range")
        return evidence.start, evidence.end
    if evidence.text is None or not evidence.text:
        raise InvalidGroundingEvidenceError("evidence requires text or start/end offsets")
    start = markdown.find(evidence.text)
    if start < 0:
        raise InvalidGroundingEvidenceError("evidence text does not occur in Markdown")
    return start, start + len(evidence.text)


__all__ = [
    "AgenticSchemaExtractor",
    "ExtractionCandidate",
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractionServiceError",
    "InvalidExtractionSchemaError",
    "InvalidGroundingEvidenceError",
    "SourceEvidence",
    "StrictSchemaViolationError",
    "TerraExtractor",
    "validate_extraction_schema",
]
