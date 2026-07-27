from __future__ import annotations

import pytest

from app.services.agentic.extraction import (
    AgenticSchemaExtractor,
    ExtractionCandidate,
    InvalidExtractionSchemaError,
    SourceEvidence,
    StrictSchemaViolationError,
)


class RecordingTerra:
    def __init__(self, candidate: ExtractionCandidate) -> None:
        self.candidate = candidate
        self.requests = []

    async def __call__(self, request):  # type: ignore[no-untyped-def]
        self.requests.append(request)
        return self.candidate


@pytest.mark.asyncio
async def test_extract_mirrors_nested_values_and_arrays_with_grounded_ranges() -> None:
    """Fails if nested leaf metadata stops matching the returned extraction."""
    markdown = "Customer: Ada\nItems: wrench, 2"
    terra = RecordingTerra(
        ExtractionCandidate(
            value={"customer": {"name": "Ada"}, "items": [{"name": "wrench", "count": 2}]},
            evidence={
                "/customer/name": [SourceEvidence(text="Ada")],
                "/items/0/name": [SourceEvidence(text="wrench")],
                "/items/0/count": [SourceEvidence(text="2")],
            },
        )
    )
    schema = {
        "type": "object",
        "properties": {
            "customer": {
                "type": "object",
                "properties": {"name": {"type": "string", "x-alternativeNames": ["Customer"]}},
                "required": ["name"],
                "additionalProperties": False,
            },
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "count": {"type": "integer"},
                    },
                    "required": ["name", "count"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["customer", "items"],
        "additionalProperties": False,
    }

    result = await AgenticSchemaExtractor(terra).extract(markdown=markdown, schema=schema)

    assert result.extraction == {
        "customer": {"name": "Ada"},
        "items": [{"name": "wrench", "count": 2}],
    }
    assert result.extraction_metadata == {
        "customer": {"name": {"value": "Ada", "ranges": [{"start": 10, "end": 13}]}},
        "items": [
            {
                "name": {"value": "wrench", "ranges": [{"start": 21, "end": 27}]},
                "count": {"value": 2, "ranges": [{"start": 29, "end": 30}]},
            }
        ],
    }
    assert terra.requests[0].schema == schema


@pytest.mark.asyncio
async def test_extract_uses_unicode_codepoint_offsets_from_provider_evidence() -> None:
    """Fails if byte offsets are accidentally used for Unicode source ranges."""
    terra = RecordingTerra(
        ExtractionCandidate(
            value={"place": "Café"},
            evidence={"/place": [SourceEvidence(text="Café", start=2, end=6)]},
        )
    )

    result = await AgenticSchemaExtractor(terra).extract(
        markdown="π Café",
        schema={
            "type": "object",
            "properties": {"place": {"type": "string"}},
            "required": ["place"],
            "additionalProperties": False,
        },
    )

    assert result.extraction_metadata["place"] == {
        "value": "Café",
        "ranges": [{"start": 2, "end": 6}],
    }


@pytest.mark.asyncio
async def test_extract_returns_schema_violation_without_rejecting_non_strict_result() -> None:
    """Fails if non-strict extraction drops usable candidate values on validation errors."""
    terra = RecordingTerra(ExtractionCandidate(value={"count": "two"}))
    schema = {
        "type": "object",
        "properties": {"count": {"type": "integer"}},
        "required": ["count"],
        "additionalProperties": False,
    }

    result = await AgenticSchemaExtractor(terra).extract(markdown="Count: two", schema=schema)

    assert result.extraction == {"count": "two"}
    assert result.schema_violation_error is not None
    assert result.warnings == ["schema_validation_failed"]
    assert result.extraction_metadata["count"] == {
        "value": "two",
        "ranges": [{"start": 7, "end": 10}],
    }


@pytest.mark.asyncio
async def test_extract_rejects_schema_violation_in_strict_mode() -> None:
    """Fails if strict mode returns a schema-invalid extraction instead of a 422-ready error."""
    terra = RecordingTerra(ExtractionCandidate(value={"count": "two"}))

    with pytest.raises(StrictSchemaViolationError) as error:
        await AgenticSchemaExtractor(terra).extract(
            markdown="Count: two",
            schema={
                "type": "object",
                "properties": {"count": {"type": "integer"}},
                "required": ["count"],
                "additionalProperties": False,
            },
            strict=True,
        )

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_extract_rejects_unsupported_or_invalid_schema_before_calling_terra() -> None:
    """Fails if unsupported schema features reach the model boundary."""
    terra = RecordingTerra(ExtractionCandidate(value={}))

    with pytest.raises(InvalidExtractionSchemaError):
        await AgenticSchemaExtractor(terra).extract(
            markdown="anything",
            schema={"type": "object", "properties": {}, "oneOf": []},
        )

    assert terra.requests == []
