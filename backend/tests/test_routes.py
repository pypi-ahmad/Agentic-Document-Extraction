"""Tests for /health, /info, /parsers, and extraction sub-endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.db_models import Document, Extraction, ExtractionSchema, ExtractionStep
from tests.conftest import _test_session_maker

# ── Helpers ──────────────────────────────────────────────────────────


async def _seed_extraction(
    *,
    status: str = "completed",
    result: dict | None = None,
    validation_errors: list[str] | None = None,
    validation_results: list[dict] | None = None,
    review_verdict: str | None = None,
    ocr_provider_used: str | None = None,
    llm_provider_used: str | None = None,
    llm_model_used: str | None = None,
    steps: list[dict] | None = None,
) -> str:
    """Insert a Document, Schema, and Extraction; return the extraction id."""
    async with _test_session_maker() as db:
        doc = Document(
            filename="test.pdf",
            original_filename="test.pdf",
            file_path="/tmp/test.pdf",
            file_type="pdf",
            file_size=1024,
        )
        schema = ExtractionSchema(
            name="Invoice",
            fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )
        db.add_all([doc, schema])
        await db.flush()

        extraction = Extraction(
            document_id=doc.id,
            schema_id=schema.id,
            status=status,
            result=result,
            validation_errors=validation_errors,
            validation_results=validation_results,
            review_verdict=review_verdict,
            ocr_provider_used=ocr_provider_used,
            llm_provider_used=llm_provider_used,
            llm_model_used=llm_model_used,
        )
        db.add(extraction)
        await db.flush()
        extraction_id = extraction.id

        if steps:
            for s in steps:
                db.add(ExtractionStep(extraction_id=extraction_id, **s))

        await db.commit()
    return extraction_id


# ── /health ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── /info ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_info(client: AsyncClient):
    resp = await client.get("/info")
    assert resp.status_code == 200
    data = resp.json()
    assert data["app_name"] == "Agentic Document Extraction"
    assert data["version"] == "0.2.0"
    assert data["python_version"]
    assert isinstance(data["pipeline_nodes"], list)
    assert "parse" in data["pipeline_nodes"]
    assert isinstance(data["ocr_providers_available"], int)
    assert isinstance(data["user_selectable_parsers_available"], int)
    assert isinstance(data["internal_parsers_available"], int)
    assert isinstance(data["llm_providers_available"], int)
    assert isinstance(data["supported_file_types"], list)
    assert "jpeg" in data["supported_file_types"]
    assert "tif" in data["supported_file_types"]
    assert data["max_upload_size_mb"] > 0
    assert isinstance(data["confidence_threshold"], float)
    assert 0.0 <= data["confidence_threshold"] <= 1.0


@pytest.mark.asyncio
async def test_info_counts_internal_runtime_parsers(client: AsyncClient):
    from types import SimpleNamespace
    from unittest.mock import patch

    def _fake_ocr_statuses(*, include_internal: bool = False):
        assert include_internal is True
        return [
            SimpleNamespace(available=True, enabled=True, user_selectable=False),
            SimpleNamespace(available=True, enabled=True, user_selectable=True),
            SimpleNamespace(available=False, enabled=True, user_selectable=True),
        ]

    with (
        patch(
            "app.services.ocr.registry.list_ocr_provider_statuses", side_effect=_fake_ocr_statuses
        ),
        patch("app.services.llm.registry.list_llm_provider_statuses", return_value=[]),
    ):
        resp = await client.get("/info")

    assert resp.status_code == 200
    assert resp.json()["ocr_providers_available"] == 2
    assert resp.json()["user_selectable_parsers_available"] == 1
    assert resp.json()["internal_parsers_available"] == 1


@pytest.mark.asyncio
async def test_info_langgraph_version(client: AsyncClient):
    resp = await client.get("/info")
    data = resp.json()
    # langgraph is installed in the test environment
    assert data["langgraph_version"] is not None


# ── /api/providers/parsers ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_parsers(client: AsyncClient):
    resp = await client.get("/api/providers/parsers")
    assert resp.status_code == 200
    parsers = resp.json()
    assert isinstance(parsers, list)
    for p in parsers:
        assert "id" in p
        assert "name" in p
        assert "enabled" in p
        assert "available" in p


@pytest.mark.asyncio
async def test_parsers_excludes_internal(client: AsyncClient):
    """Internal-only parsers (pymupdf) must never appear in the user-facing list."""
    resp = await client.get("/api/providers/parsers")
    ids = [p["id"] for p in resp.json()]
    assert "pymupdf" not in ids


# ── /api/extractions/{id}/result ─────────────────────────────────────


@pytest.mark.asyncio
async def test_get_extraction_result(client: AsyncClient):
    eid = await _seed_extraction(
        result={"vendor": "Acme"},
        llm_provider_used="openai",
        llm_model_used="gpt-4o-mini",
    )
    resp = await client.get(f"/api/extractions/{eid}/result")
    assert resp.status_code == 200
    data = resp.json()
    assert data["extraction_id"] == eid
    assert data["result"] == {"vendor": "Acme"}
    assert data["llm_provider_used"] == "openai"
    assert data["llm_model_used"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_get_extraction_result_not_found(client: AsyncClient):
    resp = await client.get("/api/extractions/nonexistent/result")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_extraction_result_pending(client: AsyncClient):
    eid = await _seed_extraction(status="pending")
    resp = await client.get(f"/api/extractions/{eid}/result")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending"
    assert data["result"] is None


# ── /api/extractions/{id}/validation ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_extraction_validation_clean(client: AsyncClient):
    eid = await _seed_extraction(
        status="completed",
        validation_errors=[],
        review_verdict="valid",
    )
    resp = await client.get(f"/api/extractions/{eid}/validation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["extraction_id"] == eid
    assert data["validation_errors"] == []
    assert data["review_verdict"] == "valid"


@pytest.mark.asyncio
async def test_get_extraction_validation_with_warnings(client: AsyncClient):
    eid = await _seed_extraction(
        status="needs_review",
        validation_errors=["Required field 'total' is missing"],
        review_verdict="needs_review",
    )
    resp = await client.get(f"/api/extractions/{eid}/validation")
    data = resp.json()
    assert data["review_verdict"] == "needs_review"
    assert len(data["validation_errors"]) == 1


@pytest.mark.asyncio
async def test_get_extraction_validation_not_found(client: AsyncClient):
    resp = await client.get("/api/extractions/nonexistent/validation")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_extraction_validation_no_errors_field(client: AsyncClient):
    """When validation_errors is NULL in DB, endpoint returns empty list."""
    eid = await _seed_extraction(status="pending", validation_errors=None)
    resp = await client.get(f"/api/extractions/{eid}/validation")
    data = resp.json()
    assert data["validation_errors"] == []
    assert data["review_verdict"] is None


# ── ExtractionResponse includes new fields ───────────────────────────


@pytest.mark.asyncio
async def test_extraction_response_includes_new_fields(client: AsyncClient):
    eid = await _seed_extraction(
        result={"k": "v"},
        validation_errors=["warn"],
        ocr_provider_used="pymupdf",
        llm_provider_used="openai",
        llm_model_used="gpt-4o-mini",
    )
    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["validation_errors"] == ["warn"]
    assert data["ocr_provider_used"] == "pymupdf"
    assert data["llm_provider_used"] == "openai"
    assert data["llm_model_used"] == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_extraction_response_normalizes_internal_ocr_provider(client: AsyncClient):
    eid = await _seed_extraction()

    async with _test_session_maker() as db:
        extraction = await db.get(Extraction, eid)
        assert extraction is not None
        extraction.ocr_provider = "pymupdf"
        await db.commit()

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    assert resp.json()["ocr_provider"] == "auto"


# ── Validation/review fields roundtrip ──────────────────────────────


@pytest.mark.asyncio
async def test_validation_results_roundtrip(client: AsyncClient):
    """validation_results and review_verdict survive the DB→API roundtrip."""
    vr = [{"field_name": "total", "valid": False, "message": "Missing"}]
    eid = await _seed_extraction(
        status="needs_review",
        validation_errors=["Missing field 'total'"],
        validation_results=vr,
        review_verdict="needs_review",
    )
    resp = await client.get(f"/api/extractions/{eid}/validation")
    assert resp.status_code == 200
    data = resp.json()
    assert data["validation_results"] == vr
    assert data["review_verdict"] == "needs_review"
    assert data["status"] == "needs_review"


@pytest.mark.asyncio
async def test_extraction_list_includes_review_fields(client: AsyncClient):
    """List endpoint returns validation_results and review_verdict."""
    vr = [{"field_name": "x", "valid": True, "message": ""}]
    eid = await _seed_extraction(
        status="completed",
        validation_results=vr,
        review_verdict="valid",
    )
    resp = await client.get("/api/extractions/")
    assert resp.status_code == 200
    items = resp.json()
    match = [e for e in items if e["id"] == eid]
    assert len(match) == 1
    assert match[0]["validation_results"] == vr
    assert match[0]["review_verdict"] == "valid"


# ── Step progress ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extraction_response_includes_steps(client: AsyncClient):
    """ExtractionResponse includes step records."""
    eid = await _seed_extraction(
        status="completed",
        steps=[
            {"name": "parse", "status": "completed", "duration_ms": 120},
            {"name": "extract", "status": "completed", "duration_ms": 1500},
            {"name": "validate", "status": "completed", "duration_ms": 10},
            {"name": "finalize", "status": "completed", "duration_ms": 2},
        ],
    )
    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["steps"]) == 4
    names = [s["name"] for s in data["steps"]]
    assert names == ["parse", "extract", "validate", "finalize"]
    assert data["steps"][1]["duration_ms"] == 1500


@pytest.mark.asyncio
async def test_extraction_response_empty_steps(client: AsyncClient):
    """ExtractionResponse returns empty steps list when no steps exist."""
    eid = await _seed_extraction(status="pending")
    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    assert resp.json()["steps"] == []


@pytest.mark.asyncio
async def test_steps_endpoint(client: AsyncClient):
    """GET /api/extractions/{id}/steps returns step records."""
    eid = await _seed_extraction(
        status="failed",
        steps=[
            {"name": "parse", "status": "completed", "duration_ms": 200},
            {"name": "extract", "status": "failed", "error": "API key invalid"},
            {"name": "validate", "status": "skipped"},
            {"name": "finalize", "status": "skipped"},
        ],
    )
    resp = await client.get(f"/api/extractions/{eid}/steps")
    assert resp.status_code == 200
    steps = resp.json()
    assert len(steps) == 4
    assert steps[0]["status"] == "completed"
    assert steps[1]["status"] == "failed"
    assert steps[1]["error"] == "API key invalid"
    assert steps[2]["status"] == "skipped"


@pytest.mark.asyncio
async def test_steps_endpoint_not_found(client: AsyncClient):
    resp = await client.get("/api/extractions/nonexistent/steps")
    assert resp.status_code == 404
