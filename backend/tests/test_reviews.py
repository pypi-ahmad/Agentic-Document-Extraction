"""Tests for the human review workflow."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.db_models import Document, Extraction, ExtractionSchema
from tests.conftest import _test_session_maker

# ── Helpers ──────────────────────────────────────────────────────────


async def _seed_review_extraction(
    *,
    status: str = "needs_review",
    result: dict | None = None,
    confidence: dict | None = None,
    validation_errors: list[str] | None = None,
    validation_results: list[dict] | None = None,
    review_verdict: str | None = "needs_review",
    started_at=None,
    completed_at=None,
) -> str:
    """Seed an extraction for review tests."""
    import datetime

    started_at = started_at or (datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=2))
    completed_at = completed_at or datetime.datetime.now(datetime.UTC)

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
            fields=[
                {
                    "name": "vendor",
                    "field_type": "string",
                    "required": True,
                    "description": "Vendor name",
                },
                {
                    "name": "total",
                    "field_type": "number",
                    "required": True,
                    "description": "Total amount",
                },
            ],
        )
        db.add_all([doc, schema])
        await db.flush()

        extraction = Extraction(
            document_id=doc.id,
            schema_id=schema.id,
            status=status,
            result=result,
            confidence=confidence,
            validation_errors=validation_errors,
            validation_results=validation_results,
            review_verdict=review_verdict,
            ocr_provider_used="pymupdf",
            llm_provider_used="openai",
            llm_model_used="gpt-4o-mini",
            started_at=started_at,
            completed_at=completed_at,
        )
        db.add(extraction)
        await db.flush()
        eid = extraction.id
        await db.commit()
    return eid


# ── Approve ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_review(client: AsyncClient):
    eid = await _seed_review_extraction(
        result={"vendor": "Acme", "total": 100},
        validation_errors=["Required field 'total' is missing"],
        validation_results=[
            {"field_name": "vendor", "valid": True, "message": ""},
            {"field_name": "total", "valid": False, "message": "Missing"},
        ],
    )
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved", "notes": "Looks fine"},
    )
    assert resp.status_code == 201
    review = resp.json()
    assert review["decision"] == "approved"
    assert review["notes"] == "Looks fine"
    assert review["extraction_id"] == eid

    # Extraction should now be completed
    ext = await client.get(f"/api/extractions/{eid}")
    data = ext.json()
    assert data["status"] == "completed"
    assert data["review_verdict"] == "approved"
    assert data["completed_at"] is not None
    assert data["validation_errors"] is None
    assert data["validation_results"] is None
    assert data["validation_summary"] is None
    assert data["error_category"] is None


# ── Corrected ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_corrected_review_merges_fields(client: AsyncClient):
    eid = await _seed_review_extraction(
        result={"vendor": "Acme", "total": None},
        confidence={"vendor": 0.93, "total": 0.21},
        validation_errors=["Required field 'total' is missing"],
        validation_results=[
            {"field_name": "vendor", "valid": True, "message": ""},
            {"field_name": "total", "valid": False, "message": "Missing"},
        ],
    )
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={
            "decision": "corrected",
            "corrected_fields": {"total": 250.00},
            "notes": "Added total from page 2",
        },
    )
    assert resp.status_code == 201
    review = resp.json()
    assert review["decision"] == "corrected"
    assert review["corrected_fields"] == {"total": 250.00}

    # Extraction result should have merged corrections
    ext = await client.get(f"/api/extractions/{eid}")
    data = ext.json()
    assert data["status"] == "completed"
    assert data["review_verdict"] == "corrected"
    assert data["result"]["vendor"] == "Acme"  # untouched
    assert data["result"]["total"] == 250.00  # corrected
    assert data["confidence"] == {"vendor": 0.93}
    assert data["validation_errors"] is None  # cleared
    assert data["validation_results"] is None
    assert data["validation_summary"] is None
    assert data["error_category"] is None


@pytest.mark.asyncio
async def test_corrected_review_requires_fields(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "Acme"})
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "corrected"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_approved_review_rejects_corrected_fields_payload(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "Acme"})
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved", "corrected_fields": {"vendor": "Other"}},
    )
    assert resp.status_code == 422
    assert any(
        "corrected_fields" in ".".join(str(part) for part in entry["loc"])
        for entry in resp.json()["detail"]
    )


# ── Rejected ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rejected_review(client: AsyncClient):
    eid = await _seed_review_extraction(
        result={"vendor": "???"},
        validation_errors=["Required field 'total' is missing"],
        validation_results=[
            {"field_name": "vendor", "valid": True, "message": ""},
            {"field_name": "total", "valid": False, "message": "Missing"},
        ],
    )
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "rejected", "notes": "Completely wrong extraction"},
    )
    assert resp.status_code == 201

    ext = await client.get(f"/api/extractions/{eid}")
    data = ext.json()
    assert data["status"] == "failed"
    assert data["review_verdict"] == "rejected"
    assert data["error"] == "Completely wrong extraction"
    assert data["error_category"] == "validation"
    assert data["validation_errors"] is None
    assert data["validation_results"] is None
    assert data["validation_summary"] is None


@pytest.mark.asyncio
async def test_rejected_review_default_error(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "???"})
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "rejected"},
    )
    assert resp.status_code == 201

    ext = await client.get(f"/api/extractions/{eid}")
    assert ext.json()["error"] == "Rejected by reviewer"
    assert ext.json()["error_category"] == "validation"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decision", "payload"),
    [
        ("approved", {"decision": "approved", "notes": "Looks good"}),
        (
            "corrected",
            {
                "decision": "corrected",
                "corrected_fields": {"total": 300.0},
                "notes": "Corrected total",
            },
        ),
        ("rejected", {"decision": "rejected", "notes": "Wrong vendor"}),
    ],
)
async def test_review_preserves_execution_timing(client: AsyncClient, decision: str, payload: dict):
    import datetime

    completed_at = datetime.datetime(2026, 4, 8, 12, 0, 0, tzinfo=datetime.UTC)
    started_at = completed_at - datetime.timedelta(seconds=4)
    eid = await _seed_review_extraction(
        result={"vendor": "Acme", "total": 100},
        validation_errors=["Required field 'total' is missing"],
        validation_results=[
            {"field_name": "vendor", "valid": True, "message": ""},
            {"field_name": "total", "valid": False, "message": "Missing"},
        ],
        started_at=started_at,
        completed_at=completed_at,
    )

    resp = await client.post(f"/api/extractions/{eid}/reviews", json=payload)
    assert resp.status_code == 201

    ext = await client.get(f"/api/extractions/{eid}")
    data = ext.json()
    observed_completed_at = datetime.datetime.fromisoformat(data["completed_at"])
    if observed_completed_at.tzinfo is None:
        observed_completed_at = observed_completed_at.replace(tzinfo=datetime.UTC)
    assert observed_completed_at == completed_at
    assert data["duration_total_ms"] == 4000
    assert data["reviewed_at"] is not None
    reviewed_at = datetime.datetime.fromisoformat(data["reviewed_at"])
    if reviewed_at.tzinfo is None:
        reviewed_at = reviewed_at.replace(tzinfo=datetime.UTC)
    assert reviewed_at >= completed_at


# ── Guards ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_review_completed_extraction(client: AsyncClient):
    eid = await _seed_review_extraction(
        status="completed",
        result={"vendor": "Acme"},
        review_verdict="valid",
    )
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved"},
    )
    assert resp.status_code == 409
    assert "needs_review" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cannot_review_failed_extraction(client: AsyncClient):
    eid = await _seed_review_extraction(status="failed", review_verdict=None)
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_review_extraction_not_found(client: AsyncClient):
    resp = await client.post(
        "/api/extractions/nonexistent/reviews",
        json={"decision": "approved"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_decision(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "Acme"})
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "maybe"},
    )
    assert resp.status_code == 422


# ── List reviews ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_reviews_empty(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "Acme"})
    resp = await client.get(f"/api/extractions/{eid}/reviews")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_reviews_after_submit(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "Acme"})
    await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved", "notes": "LGTM"},
    )
    resp = await client.get(f"/api/extractions/{eid}/reviews")
    assert resp.status_code == 200
    reviews = resp.json()
    assert len(reviews) == 1
    assert reviews[0]["decision"] == "approved"
    assert reviews[0]["notes"] == "LGTM"


@pytest.mark.asyncio
async def test_list_reviews_not_found(client: AsyncClient):
    resp = await client.get("/api/extractions/nonexistent/reviews")
    assert resp.status_code == 404


# ── Reviews in ExtractionResponse ────────────────────────────────────


@pytest.mark.asyncio
async def test_extraction_response_includes_reviews(client: AsyncClient):
    eid = await _seed_review_extraction(result={"vendor": "Acme"})
    await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved"},
    )
    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()
    assert "reviews" in data
    assert len(data["reviews"]) == 1
    assert data["reviews"][0]["decision"] == "approved"
