"""Tests for extraction schema CRUD endpoints."""

import pytest
from httpx import AsyncClient

SAMPLE_SCHEMA = {
    "name": "Invoice",
    "description": "Extract invoice data",
    "fields": [
        {
            "name": "vendor_name",
            "description": "Name of the vendor",
            "field_type": "string",
            "required": True,
        },
        {
            "name": "total_amount",
            "description": "Total invoice amount",
            "field_type": "number",
            "required": True,
        },
        {
            "name": "invoice_date",
            "description": "Date of the invoice",
            "field_type": "date",
            "required": False,
        },
    ],
}


@pytest.mark.asyncio
async def test_create_schema(client: AsyncClient):
    resp = await client.post("/api/schemas/", json=SAMPLE_SCHEMA)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Invoice"
    assert len(data["fields"]) == 3


@pytest.mark.asyncio
async def test_list_schemas(client: AsyncClient):
    await client.post("/api/schemas/", json=SAMPLE_SCHEMA)
    resp = await client.get("/api/schemas/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_update_schema(client: AsyncClient):
    create_resp = await client.post("/api/schemas/", json=SAMPLE_SCHEMA)
    schema_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/schemas/{schema_id}",
        json={"name": "Updated Invoice"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated Invoice"


@pytest.mark.asyncio
async def test_delete_schema(client: AsyncClient):
    create_resp = await client.post("/api/schemas/", json=SAMPLE_SCHEMA)
    schema_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/schemas/{schema_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/api/schemas/{schema_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_schema_missing_fields(client: AsyncClient):
    resp = await client.post("/api/schemas/", json={"name": "Bad", "fields": []})
    assert resp.status_code == 422  # validation error — min_length=1
