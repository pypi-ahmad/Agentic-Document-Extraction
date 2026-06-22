"""Integration tests for the extraction lifecycle.

These tests exercise the full path:
  POST /api/extractions → background pipeline → GET status/result/validation/steps

OCR and LLM providers are replaced with fast test doubles so the tests
stay hermetic and run in milliseconds while still exercising the real
LangGraph pipeline, step-level persistence, validation engine, and API
serialisation.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.db_models import Document, Extraction, ExtractionSchema
from app.services.llm.base import ExtractionResult
from app.services.ocr.base import OCRResult
from tests.conftest import _test_session_maker

# ── Test doubles ─────────────────────────────────────────────────────


class _FakeOCR:
    """Returns canned OCR text."""

    def __init__(self, text: str = "Invoice from Acme Corp. Total: $1,250.00") -> None:
        self._text = text

    async def extract_text(self, file_path: Path) -> OCRResult:
        return OCRResult(text=self._text, pages=[self._text], provider="fake-ocr")


class _FakeLLM:
    """Returns canned extraction data, optionally with missing fields."""

    def __init__(
        self,
        data: dict | None = None,
        confidence: dict | None = None,
    ) -> None:
        self._data = data or {"vendor": "Acme Corp", "total": 1250.00}
        self._confidence = confidence or {}

    async def extract(
        self,
        text: str,
        schema_fields: list[dict],
        model_id: str = "auto",
    ) -> ExtractionResult:
        return ExtractionResult(
            data=self._data,
            raw_response=str(self._data),
            model_used="fake-model",
            provider="fake-llm",
            confidence=self._confidence,
        )


class _FailingLLM:
    """Always raises during extraction."""

    async def extract(self, text: str, schema_fields: list[dict], model_id: str = "auto"):
        from app.services.llm.base import LLMProviderError

        raise LLMProviderError("fake-llm", "Simulated LLM failure", code="provider_error")


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed(tmp_path: Path) -> dict:
    """Seed a Document and ExtractionSchema and return their ids + file path.

    Creates a minimal PDF file on disk so the ``parse_node`` file-exists
    check passes.
    """
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 test invoice content")

    async with _test_session_maker() as db:
        doc = Document(
            filename="invoice.pdf",
            original_filename="invoice.pdf",
            file_path=str(pdf),
            file_type="pdf",
            file_size=len(pdf.read_bytes()),
        )
        schema = ExtractionSchema(
            name=f"Invoice-{uuid.uuid4().hex[:8]}",
            fields=[
                {"name": "vendor", "field_type": "string", "required": True},
                {"name": "total", "field_type": "number", "required": True},
                {"name": "notes", "field_type": "string", "required": False},
            ],
        )
        db.add_all([doc, schema])
        await db.flush()
        ids = {"document_id": doc.id, "schema_id": schema.id, "file_path": str(pdf)}
        await db.commit()
    return ids


def _provider_patches(
    ocr: _FakeOCR | None = None,
    llm: _FakeLLM | _FailingLLM | None = None,
):
    """Return context managers that patch OCR/LLM registries + async_session."""
    ocr_inst = ocr or _FakeOCR()
    llm_inst = llm or _FakeLLM()
    return (
        patch("app.routers.extractions.async_session", _test_session_maker),
        patch("app.main.async_session", _test_session_maker),
        patch(
            "app.services.ocr.registry.get_ocr_provider",
            lambda pid, *, file_path=None: ocr_inst,
        ),
        patch(
            "app.services.llm.registry.get_llm_provider",
            lambda pid: llm_inst,
        ),
    )


async def _submit_and_run(
    client: AsyncClient,
    seed: dict,
    *,
    ocr: _FakeOCR | None = None,
    llm: _FakeLLM | _FailingLLM | None = None,
) -> str:
    """POST an extraction and return its id.

    HTTPX's ASGITransport runs FastAPI BackgroundTasks inline during the
    request, so the pipeline completes before the response is returned.
    The provider patches must be active for the background task to use
    the test doubles and the test DB session.
    """
    patches = _provider_patches(ocr=ocr, llm=llm)

    with patches[0], patches[1], patches[2], patches[3]:
        resp = await client.post(
            "/api/extractions/",
            json={"document_id": seed["document_id"], "schema_id": seed["schema_id"]},
        )
        assert resp.status_code == 202, resp.text

    return resp.json()["id"]


# ── Happy path: submit → process → validate → fetch ─────────────────


@pytest.mark.asyncio
async def test_submission_commits_queued_job_before_background_execution(
    client: AsyncClient,
    seed: dict,
) -> None:
    """Background execution sees a durably committed queued row."""

    async def _assert_committed(extraction_id: str) -> None:
        async with _test_session_maker() as db:
            extraction = await db.get(Extraction, extraction_id)
            assert extraction is not None
            assert extraction.status == "queued"
            assert extraction.started_at is None
            assert extraction.completed_at is None
            assert extraction.error is None

    runner = AsyncMock(side_effect=_assert_committed)

    with patch("app.routers.extractions._run_extraction_job", new=runner):
        resp = await client.post(
            "/api/extractions/",
            json={"document_id": seed["document_id"], "schema_id": seed["schema_id"]},
        )

    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "queued"
    assert data["steps"] == []
    assert data["started_at"] is None
    assert data["completed_at"] is None
    assert data["created_at"] is not None
    runner.assert_awaited_once_with(data["id"])


@pytest.mark.asyncio
async def test_happy_path_completed(client: AsyncClient, seed: dict) -> None:
    """Full lifecycle: all required fields present → status completed."""
    eid = await _submit_and_run(client, seed)

    # GET extraction full
    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "completed"
    assert data["error"] is None
    assert data["result"]["vendor"] == "Acme Corp"
    assert data["result"]["total"] == 1250.00
    assert data["ocr_provider_used"] == "fake-ocr"
    assert data["llm_provider_used"] == "fake-llm"
    assert data["llm_model_used"] == "fake-model"
    assert data["completed_at"] is not None

    # Steps should be recorded (7 in the v0.4.0 pipeline: triage, parse,
    # extract, validate, reflect, await_review, finalize).
    assert len(data["steps"]) == 7
    step_names = [s["name"] for s in data["steps"]]
    assert step_names == [
        "triage",
        "parse",
        "extract",
        "validate",
        "reflect",
        "await_review",
        "finalize",
    ]
    for step in data["steps"]:
        assert step["status"] == "completed"
        assert step["duration_ms"] is not None
        assert step["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_happy_path_result_endpoint(client: AsyncClient, seed: dict) -> None:
    """GET /result returns the extraction data slice."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}/result")
    assert resp.status_code == 200
    data = resp.json()

    assert data["extraction_id"] == eid
    assert data["status"] == "completed"
    assert data["result"]["vendor"] == "Acme Corp"
    assert data["ocr_provider_used"] == "fake-ocr"


@pytest.mark.asyncio
async def test_happy_path_validation_clean(client: AsyncClient, seed: dict) -> None:
    """GET /validation returns no errors when all fields are valid."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}/validation")
    assert resp.status_code == 200
    data = resp.json()

    assert data["extraction_id"] == eid
    assert data["validation_errors"] == []
    assert data["review_verdict"] == "valid"


@pytest.mark.asyncio
async def test_happy_path_steps_endpoint(client: AsyncClient, seed: dict) -> None:
    """GET /steps returns individual step records."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}/steps")
    assert resp.status_code == 200
    steps = resp.json()

    # 7 steps in the happy path: triage, parse, extract, validate,
    # reflect, await_review, finalize. (The reflect and await_review
    # nodes run as no-ops when validation already passed.)
    assert len(steps) == 7
    assert all(s["status"] == "completed" for s in steps)
    assert steps[0]["name"] == "triage"
    assert steps[-1]["name"] == "finalize"


# ── Needs-review: missing required field ─────────────────────────────


@pytest.mark.asyncio
async def test_needs_review_missing_field(client: AsyncClient, seed: dict) -> None:
    """Missing a required field → needs_review with validation errors."""
    # LLM omits 'total' (required field)
    llm = _FakeLLM(data={"vendor": "Acme Corp"})
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "needs_review"
    assert data["review_verdict"] == "needs_review"
    assert any("total" in err for err in data["validation_errors"])
    assert data["result"] == {"vendor": "Acme Corp"}
    assert data["completed_at"] is not None

    # Steps include a reflect round (the v0.4.0 reflection loop).
    step_names = [s["name"] for s in data["steps"]]
    assert "parse" in step_names
    assert "extract" in step_names
    assert "validate" in step_names
    assert "reflect" in step_names
    assert "finalize" in step_names
    # All steps ran to completion (no failed/skipped).
    assert all(s["status"] in ("completed", "running") for s in data["steps"])
    assert all(s["status"] == "completed" for s in data["steps"])


# ── Failure: LLM error → failed + skipped steps ─────────────────────


@pytest.mark.asyncio
async def test_llm_failure(client: AsyncClient, seed: dict) -> None:
    """LLM provider error → status failed, downstream steps skipped."""
    eid = await _submit_and_run(client, seed, llm=_FailingLLM())

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "failed"
    assert "Simulated LLM failure" in data["error"]
    assert data["result"] is None
    assert data["completed_at"] is not None  # failed jobs still record when they finished

    steps = data["steps"]
    # 7 steps total now: parse, extract, validate, reflect, await_review, finalize.
    assert len(steps) == 7
    step_map = {s["name"]: s["status"] for s in steps}
    assert step_map["parse"] == "completed"
    assert step_map["extract"] == "failed"
    assert step_map["validate"] == "skipped"
    assert step_map["finalize"] == "skipped"


# ── Failure: parse error → all downstream skipped ────────────────────


@pytest.mark.asyncio
async def test_parse_failure_missing_file(client: AsyncClient) -> None:
    """Non-existent file → parse fails, all downstream steps skipped."""
    async with _test_session_maker() as db:
        doc = Document(
            filename="gone.pdf",
            original_filename="gone.pdf",
            file_path="/tmp/does_not_exist.pdf",
            file_type="pdf",
            file_size=0,
        )
        schema = ExtractionSchema(
            name=f"Test-{uuid.uuid4().hex[:8]}",
            fields=[{"name": "x", "field_type": "string", "required": True}],
        )
        db.add_all([doc, schema])
        await db.flush()
        seed = {"document_id": doc.id, "schema_id": schema.id}
        await db.commit()

    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "failed"
    assert "not found" in data["error"].lower()

    steps = data["steps"]
    step_map = {s["name"]: s["status"] for s in steps}
    assert step_map["parse"] == "failed"
    assert step_map["extract"] == "skipped"
    assert step_map["validate"] == "skipped"
    assert step_map["finalize"] == "skipped"


# ── Retry lifecycle ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retry_after_failure(client: AsyncClient, seed: dict) -> None:
    """Failed job can be retried and succeeds with working providers."""
    # First run: LLM fails
    eid = await _submit_and_run(client, seed, llm=_FailingLLM())

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.json()["status"] == "failed"

    # Retry: now with working LLM (background task runs inline via ASGITransport)
    patches = _provider_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        resp = await client.post(f"/api/extractions/{eid}/retry")
        assert resp.status_code == 202

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "completed"
    assert data["result"]["vendor"] == "Acme Corp"
    assert data["error"] is None

    # Steps reset: should have 7 fresh completed steps (not 14)
    assert len(data["steps"]) == 7
    assert all(s["status"] == "completed" for s in data["steps"])


# ── List endpoint reflects integration state ─────────────────────────


@pytest.mark.asyncio
async def test_list_extractions_after_run(client: AsyncClient, seed: dict) -> None:
    """GET /api/extractions/ includes the completed extraction."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get("/api/extractions/")
    assert resp.status_code == 200
    items = resp.json()

    match = [e for e in items if e["id"] == eid]
    assert len(match) == 1
    assert match[0]["status"] == "completed"
    assert match[0]["result"]["vendor"] == "Acme Corp"
    # 7 steps in the v0.4.0 pipeline.
    assert len(match[0]["steps"]) == 7


# ── Computed fields ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duration_total_ms_computed(client: AsyncClient, seed: dict) -> None:
    """ExtractionResponse includes computed duration_total_ms."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["duration_total_ms"] is not None
    assert isinstance(data["duration_total_ms"], int)
    assert data["duration_total_ms"] >= 0


@pytest.mark.asyncio
async def test_validation_summary_all_passed(client: AsyncClient, seed: dict) -> None:
    """validation_summary reports all checks passed when no failures."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["validation_summary"] is not None
    assert "passed" in data["validation_summary"].lower()


@pytest.mark.asyncio
async def test_validation_summary_with_failures(client: AsyncClient, seed: dict) -> None:
    """validation_summary notes failures when required fields are missing."""
    llm = _FakeLLM(data={"vendor": "Acme Corp"})  # missing 'total'
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["validation_summary"] is not None
    assert "attention" in data["validation_summary"].lower()


# ── Review workflow ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_approve(client: AsyncClient, seed: dict) -> None:
    """Approving a needs_review extraction transitions it to completed."""
    llm = _FakeLLM(data={"vendor": "Acme Corp"})  # missing 'total'
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.json()["status"] == "needs_review"

    # Submit approval
    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved", "notes": "Looks fine, total not needed"},
    )
    assert resp.status_code == 201
    review = resp.json()
    assert review["decision"] == "approved"
    assert review["notes"] == "Looks fine, total not needed"

    # Extraction is now completed
    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()
    assert data["status"] == "completed"
    assert data["review_verdict"] == "approved"
    assert data["completed_at"] is not None
    assert len(data["reviews"]) == 1


@pytest.mark.asyncio
async def test_review_correct(client: AsyncClient, seed: dict) -> None:
    """Correcting a needs_review extraction merges fields and completes."""
    llm = _FakeLLM(data={"vendor": "Acme Corp"})  # missing 'total'
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={
            "decision": "corrected",
            "corrected_fields": {"total": 999.99},
            "notes": "Added missing total",
        },
    )
    assert resp.status_code == 201

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()
    assert data["status"] == "completed"
    assert data["review_verdict"] == "corrected"
    assert data["result"]["total"] == 999.99
    assert data["result"]["vendor"] == "Acme Corp"
    assert data["validation_errors"] is None  # cleared on correction


@pytest.mark.asyncio
async def test_review_reject(client: AsyncClient, seed: dict) -> None:
    """Rejecting a needs_review extraction transitions it to failed."""
    llm = _FakeLLM(data={"vendor": "Acme Corp"})
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "rejected", "notes": "Completely wrong document"},
    )
    assert resp.status_code == 201

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()
    assert data["status"] == "failed"
    assert data["review_verdict"] == "rejected"
    assert data["error"] == "Completely wrong document"


@pytest.mark.asyncio
async def test_review_on_non_review_extraction_rejected(client: AsyncClient, seed: dict) -> None:
    """Cannot review an extraction that is not in needs_review state."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.json()["status"] == "completed"

    resp = await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_review_history_listed(client: AsyncClient, seed: dict) -> None:
    """GET /reviews returns the decision history."""
    llm = _FakeLLM(data={"vendor": "Acme Corp"})
    eid = await _submit_and_run(client, seed, llm=llm)

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


# ── Step progress details ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_steps_have_timing(client: AsyncClient, seed: dict) -> None:
    """Every completed step has started_at, completed_at, and duration_ms."""
    eid = await _submit_and_run(client, seed)

    resp = await client.get(f"/api/extractions/{eid}/steps")
    steps = resp.json()

    for step in steps:
        assert step["status"] == "completed"
        assert step["started_at"] is not None
        assert step["completed_at"] is not None
        assert step["duration_ms"] is not None
        assert step["duration_ms"] >= 0
        assert step["error"] is None


# ── Confidence-driven routing (end-to-end) ───────────────────────────


@pytest.mark.asyncio
async def test_low_confidence_routes_to_needs_review(client: AsyncClient, seed: dict) -> None:
    """LLM returning low confidence on a field triggers needs_review status."""
    llm = _FakeLLM(
        data={"vendor": "Acme Corp", "total": 1250.00},
        confidence={"vendor": 0.9, "total": 0.3},  # total below threshold
    )
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "needs_review"
    assert data["review_verdict"] == "needs_review"
    # The low-confidence field should appear in validation_results
    assert data["validation_results"] is not None
    low_fields = [e["field_name"] for e in data["validation_results"] if not e["valid"]]
    assert "total" in low_fields


@pytest.mark.asyncio
async def test_high_confidence_completes(client: AsyncClient, seed: dict) -> None:
    """All fields above threshold → status completed (no review routing)."""
    llm = _FakeLLM(
        data={"vendor": "Acme Corp", "total": 1250.00},
        confidence={"vendor": 0.95, "total": 0.85},
    )
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "completed"
    assert data["review_verdict"] == "valid"


# ── reviewed_at and error_category lifecycle ─────────────────────────


@pytest.mark.asyncio
async def test_reviewed_at_set_on_review(client: AsyncClient, seed: dict) -> None:
    """reviewed_at is populated after a review decision."""
    llm = _FakeLLM(data={"vendor": "Acme Corp"})  # missing total → needs_review
    eid = await _submit_and_run(client, seed, llm=llm)

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.json()["reviewed_at"] is None

    await client.post(
        f"/api/extractions/{eid}/reviews",
        json={"decision": "approved"},
    )

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()
    assert data["reviewed_at"] is not None
    assert data["status"] == "completed"


@pytest.mark.asyncio
async def test_error_category_set_on_failure(client: AsyncClient, seed: dict) -> None:
    """Failed extraction gets an error_category for triage."""
    eid = await _submit_and_run(client, seed, llm=_FailingLLM())

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()

    assert data["status"] == "failed"
    assert data["error_category"] is not None
    assert data["error_category"] in (
        "auth",
        "rate_limit",
        "timeout",
        "parse_error",
        "provider_error",
        "file_error",
        "validation",
        "unknown",
    )


@pytest.mark.asyncio
async def test_retry_clears_error_category_and_reviewed_at(client: AsyncClient, seed: dict) -> None:
    """Retrying a failed extraction clears error_category and reviewed_at."""
    eid = await _submit_and_run(client, seed, llm=_FailingLLM())

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.json()["error_category"] is not None

    # Retry with a working LLM
    patches = _provider_patches()
    with patches[0], patches[1], patches[2], patches[3]:
        resp = await client.post(f"/api/extractions/{eid}/retry")
        assert resp.status_code == 202

    resp = await client.get(f"/api/extractions/{eid}")
    data = resp.json()
    assert data["error_category"] is None
    assert data["reviewed_at"] is None
