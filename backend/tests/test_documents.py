"""Tests for document upload and CRUD endpoints."""

import io

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_upload_document(client: AsyncClient):
    pdf_bytes = b"%PDF-1.4 fake content"
    resp = await client.post(
        "/api/documents/",
        files={"file": ("test.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["original_filename"] == "test.pdf"
    assert data["file_type"] == "pdf"
    assert data["status"] == "uploaded"


@pytest.mark.asyncio
async def test_upload_invalid_type(client: AsyncClient):
    resp = await client.post(
        "/api/documents/",
        files={"file": ("test.exe", io.BytesIO(b"bad"), "application/octet-stream")},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_documents(client: AsyncClient):
    resp = await client.get("/api/documents/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient):
    resp = await client.get("/api/documents/nonexistent")
    assert resp.status_code == 404
