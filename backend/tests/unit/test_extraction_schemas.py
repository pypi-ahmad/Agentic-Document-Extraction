import pytest

from app.services.parsing.extraction_schemas import validate_extraction_schema

INVOICE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "invoice_number": {"type": "string", "description": "Invoice identifier"},
        "vendor": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "line_items": {
            "type": "array",
            "x-paperplane-kind": "table",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": "number"},
                },
                "required": ["description", "amount"],
            },
        },
    },
    "required": ["invoice_number", "line_items"],
}


def test_schema_validator_normalizes_nested_objects_and_tables() -> None:
    result = validate_extraction_schema(INVOICE_SCHEMA)

    assert result.valid is True
    assert result.errors == []
    assert result.normalized_schema is not None
    assert result.normalized_schema["additionalProperties"] is False
    assert result.normalized_schema["properties"]["vendor"]["additionalProperties"] is False
    assert (
        result.normalized_schema["properties"]["line_items"]["items"]["additionalProperties"]
        is False
    )


@pytest.mark.parametrize("keyword", ["$ref", "oneOf", "allOf", "anyOf", "if", "pattern"])
def test_schema_validator_rejects_unsupported_composition(keyword: str) -> None:
    schema = {
        "type": "object",
        "properties": {
            "value": {
                "type": "string",
                keyword: (
                    "^(a+)+$"
                    if keyword == "pattern"
                    else ([] if keyword != "$ref" else "remote.json")
                ),
            }
        },
    }

    result = validate_extraction_schema(schema)

    assert result.valid is False
    assert any(error.code == "unsupported_keyword" for error in result.errors)


def test_table_annotation_requires_array_of_objects() -> None:
    result = validate_extraction_schema(
        {
            "type": "object",
            "properties": {
                "rows": {
                    "type": "array",
                    "x-paperplane-kind": "table",
                    "items": {"type": "string"},
                }
            },
        }
    )

    assert result.valid is False
    assert any(error.code == "invalid_table_schema" for error in result.errors)
