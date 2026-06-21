"""Tests for the document-type presets module and API endpoints."""

import pytest
from httpx import AsyncClient

from app.services.extraction.presets import (
    get_preset,
    list_presets,
)

# ── Unit tests for presets module ────────────────────────────────────


class TestPresetsModule:
    def test_list_presets_returns_all(self):
        presets = list_presets()
        assert len(presets) == 4
        ids = {p.id for p in presets}
        assert ids == {
            "preset-invoice",
            "preset-receipt",
            "preset-purchase-order",
            "preset-bank-statement",
        }

    def test_get_preset_valid(self):
        preset = get_preset("preset-invoice")
        assert preset is not None
        assert preset.name == "Invoice"
        assert len(preset.fields) == 10

    def test_get_preset_receipt(self):
        preset = get_preset("preset-receipt")
        assert preset is not None
        assert preset.name == "Receipt"
        assert len(preset.fields) == 7

    def test_get_preset_purchase_order(self):
        preset = get_preset("preset-purchase-order")
        assert preset is not None
        assert preset.name == "Purchase Order"
        assert len(preset.fields) == 10

    def test_get_preset_bank_statement(self):
        preset = get_preset("preset-bank-statement")
        assert preset is not None
        assert preset.name == "Bank Statement"
        assert len(preset.fields) == 9

    def test_get_preset_invalid(self):
        assert get_preset("nonexistent") is None

    def test_preset_fields_have_required_attrs(self):
        for preset in list_presets():
            for f in preset.fields:
                assert f.name
                assert f.description
                assert f.field_type in ("string", "number", "date", "list", "boolean", "object")

    def test_presets_are_frozen(self):
        preset = get_preset("preset-invoice")
        with pytest.raises(AttributeError):
            preset.name = "Modified"  # type: ignore[misc]


# ── API endpoint tests ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_presets_endpoint(client: AsyncClient):
    resp = await client.get("/api/schemas/presets")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 4
    ids = {p["id"] for p in data}
    assert ids == {
        "preset-invoice",
        "preset-receipt",
        "preset-purchase-order",
        "preset-bank-statement",
    }
    for preset in data:
        assert "name" in preset
        assert "description" in preset
        assert "doc_type" in preset
        assert "fields" in preset
        assert len(preset["fields"]) > 0


@pytest.mark.asyncio
async def test_create_from_preset_invoice(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/presets/preset-invoice",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Invoice"
    assert len(data["fields"]) == 10
    field_names = {f["name"] for f in data["fields"]}
    assert "vendor_name" in field_names
    assert "total_amount" in field_names
    assert data["id"]  # has a DB id


@pytest.mark.asyncio
async def test_create_from_preset_receipt(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/presets/preset-receipt",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Receipt"
    assert len(data["fields"]) == 7


@pytest.mark.asyncio
async def test_create_from_preset_custom_name(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/presets/preset-invoice",
        json={"name": "My Custom Invoice"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "My Custom Invoice"


@pytest.mark.asyncio
async def test_create_from_preset_not_found(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/presets/nonexistent",
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_from_preset_legacy_alias_still_works(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/from-preset",
        json={"preset_id": "preset-invoice"},
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "Invoice"


@pytest.mark.asyncio
async def test_create_from_preset_duplicate_name_is_conflict(client: AsyncClient):
    first = await client.post(
        "/api/schemas/presets/preset-invoice",
    )
    assert first.status_code == 201

    second = await client.post(
        "/api/schemas/presets/preset-invoice",
    )
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


@pytest.mark.asyncio
async def test_create_schema_duplicate_name_is_conflict(client: AsyncClient):
    payload = {
        "name": "Invoice Contract",
        "fields": [
            {
                "name": "vendor_name",
                "description": "Vendor",
                "field_type": "string",
                "required": True,
            },
        ],
    }
    first = await client.post("/api/schemas/", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/schemas/", json=payload)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


@pytest.mark.asyncio
async def test_update_schema_duplicate_name_is_conflict(client: AsyncClient):
    alpha = await client.post(
        "/api/schemas/",
        json={
            "name": "Alpha Schema",
            "fields": [
                {
                    "name": "vendor_name",
                    "description": "Vendor",
                    "field_type": "string",
                    "required": True,
                },
            ],
        },
    )
    beta = await client.post(
        "/api/schemas/",
        json={
            "name": "Beta Schema",
            "fields": [
                {
                    "name": "invoice_number",
                    "description": "Invoice",
                    "field_type": "string",
                    "required": True,
                },
            ],
        },
    )
    assert alpha.status_code == 201
    assert beta.status_code == 201

    resp = await client.put(
        f"/api/schemas/{beta.json()['id']}",
        json={"name": "Alpha Schema"},
    )
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_schema_duplicate_field_names_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/",
        json={
            "name": "Duplicate Fields",
            "fields": [
                {"name": "total", "description": "Total", "field_type": "number", "required": True},
                {
                    "name": "TOTAL",
                    "description": "Total again",
                    "field_type": "number",
                    "required": False,
                },
            ],
        },
    )
    assert resp.status_code == 422
    assert "Field names must be unique" in resp.text


@pytest.mark.asyncio
async def test_create_schema_whitespace_only_name_rejected(client: AsyncClient):
    resp = await client.post(
        "/api/schemas/",
        json={
            "name": "   ",
            "fields": [
                {
                    "name": "vendor_name",
                    "description": "Vendor",
                    "field_type": "string",
                    "required": True,
                },
            ],
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preset_schema_appears_in_list(client: AsyncClient):
    await client.post(
        "/api/schemas/presets/preset-invoice",
    )
    resp = await client.get("/api/schemas/")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert "Invoice" in names
