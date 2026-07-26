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
        result.normalized_schema["properties"]["line_items"]["items"][
            "additionalProperties"
        ]
        is False
    )


@pytest.mark.parametrize("keyword", ["$ref", "oneOf", "allOf", "anyOf", "if"])
def test_schema_validator_rejects_unsupported_composition(keyword: str) -> None:
    schema = {
        "type": "object",
        "properties": {"value": {keyword: [] if keyword != "$ref" else "remote.json"}},
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


@pytest.mark.asyncio
async def test_extraction_schema_crud_versions_definitions(client) -> None:
    created = await client.post(
        "/api/extraction-schemas",
        json={"name": "Invoice", "description": "Invoice fields", "json_schema": INVOICE_SCHEMA},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["version"] == 1
    assert len(body["schema_sha256"]) == 64

    listed = await client.get("/api/extraction-schemas")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [body["id"]]

    renamed = await client.put(
        f"/api/extraction-schemas/{body['id']}",
        json={"name": "Invoice v2", "description": "Renamed", "json_schema": INVOICE_SCHEMA},
    )
    assert renamed.status_code == 200
    assert renamed.json()["version"] == 1

    changed_schema = {**INVOICE_SCHEMA, "required": ["invoice_number"]}
    updated = await client.put(
        f"/api/extraction-schemas/{body['id']}",
        json={"name": "Invoice v2", "description": "Renamed", "json_schema": changed_schema},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2

    deleted = await client.delete(f"/api/extraction-schemas/{body['id']}")
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_extraction_schema_validate_endpoint_is_non_mutating(client) -> None:
    response = await client.post(
        "/api/extraction-schemas/validate", json={"json_schema": INVOICE_SCHEMA}
    )

    assert response.status_code == 200
    assert response.json()["valid"] is True
    listed = await client.get("/api/extraction-schemas")
    assert listed.json()["items"] == []


@pytest.mark.asyncio
async def test_extraction_schema_names_are_case_insensitively_unique(client) -> None:
    first = await client.post(
        "/api/extraction-schemas", json={"name": "Invoice", "json_schema": INVOICE_SCHEMA}
    )
    assert first.status_code == 201

    duplicate = await client.post(
        "/api/extraction-schemas", json={"name": " invoice ", "json_schema": INVOICE_SCHEMA}
    )
    assert duplicate.status_code == 409
