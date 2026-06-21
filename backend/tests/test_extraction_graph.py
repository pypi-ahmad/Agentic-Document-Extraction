"""Tests for the LangGraph extraction pipeline."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import pytest

from app.services.extraction.graph import (
    PipelineState,
    build_extraction_graph,
    extract_node,
    finalize_node,
    parse_node,
    run_extraction,
    validate_node,
)
from app.services.ocr.base import OCRResult

# ── Helpers ──────────────────────────────────────────────────────────


def _state(**overrides: Any) -> PipelineState:
    """Build a minimal PipelineState dict with sensible defaults."""
    base: PipelineState = {
        "file_path": "sample.pdf",
        "schema_fields": [],
        "ocr_provider_id": "auto",
        "llm_provider_id": "auto",
        "llm_model_id": "auto",
        "status": "pending",
        "error": "",
    }
    base.update(overrides)
    return base


# ── Parse node ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_node_missing_file():
    result = await parse_node(_state(file_path="nonexistent.pdf"))
    assert result["status"] == "failed"
    assert "not found" in result["error"].lower()


@pytest.mark.asyncio
async def test_parse_node_calls_registry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    captured: dict[str, Any] = {}
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    class DummyProvider:
        async def extract_text(self, file_path: Path) -> OCRResult:
            captured["path"] = file_path
            return OCRResult(text="hello world", pages=["hello world"], provider="dummy")

    def fake_get(provider_id: str, *, file_path: Path | None = None) -> DummyProvider:
        captured["provider_id"] = provider_id
        captured["registry_path"] = file_path
        return DummyProvider()

    monkeypatch.setattr("app.services.ocr.registry.get_ocr_provider", fake_get)

    result = await parse_node(_state(file_path=str(pdf), ocr_provider_id="auto"))
    assert result["status"] == "ocr_complete"
    assert result["ocr_text"] == "hello world"
    assert result["ocr_provider_used"] == "dummy"
    assert captured["provider_id"] == "auto"


@pytest.mark.asyncio
async def test_parse_node_fails_cleanly(tmp_path: Path):
    """Auto OCR for image without image OCR enabled → failure."""
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG")
    result = await parse_node(_state(file_path=str(img), ocr_provider_id="auto"))
    assert result["status"] == "failed"
    assert result["error"]


# ── Extract node ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_node_calls_provider(monkeypatch: pytest.MonkeyPatch):
    from app.services.llm.base import ExtractionResult

    class DummyLLM:
        async def extract(
            self, text: str, schema_fields: list[dict], model_id: str = "auto"
        ) -> ExtractionResult:
            return ExtractionResult(
                data={"vendor": "Acme"},
                raw_response='{"vendor":"Acme"}',
                model_used="test-model",
                provider="test-llm",
            )

    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: DummyLLM(),
    )

    result = await extract_node(
        _state(
            ocr_text="Invoice from Acme",
            schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )
    )
    assert result["status"] == "extracted"
    assert result["extracted_data"]["vendor"] == "Acme"
    assert result["llm_provider_used"] == "test-llm"


@pytest.mark.asyncio
async def test_extract_node_handles_error(monkeypatch: pytest.MonkeyPatch):
    from app.services.llm.base import LLMProviderError

    def raise_error(pid: str):
        raise LLMProviderError("test", "boom", code="provider_error")

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", raise_error)

    result = await extract_node(_state(ocr_text="text"))
    assert result["status"] == "failed"
    assert "boom" in result["error"]


# ── Validate node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_all_present():
    result = await validate_node(
        _state(
            extracted_data={"vendor": "Acme", "total": 100},
            schema_fields=[
                {"name": "vendor", "required": True, "field_type": "string"},
                {"name": "total", "required": True, "field_type": "number"},
            ],
        )
    )
    assert result["validation_errors"] == []
    assert result["review_verdict"] == "valid"
    assert isinstance(result["validation_results"], list)


@pytest.mark.asyncio
async def test_validate_missing_required():
    result = await validate_node(
        _state(
            extracted_data={"vendor": "Acme"},
            schema_fields=[
                {"name": "vendor", "required": True, "field_type": "string"},
                {"name": "total", "required": True, "field_type": "number"},
            ],
        )
    )
    assert len(result["validation_errors"]) >= 1
    assert any("total" in e for e in result["validation_errors"])
    assert result["review_verdict"] == "needs_review"


@pytest.mark.asyncio
async def test_validate_optional_missing_ok():
    result = await validate_node(
        _state(
            extracted_data={},
            schema_fields=[{"name": "notes", "required": False}],
        )
    )
    assert result["validation_errors"] == []
    assert result["review_verdict"] == "valid"


# ── Finalize node ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_completed():
    result = await finalize_node(_state(review_verdict="valid"))
    assert result["status"] == "completed"
    assert result["completed_at"]
    datetime.datetime.fromisoformat(result["completed_at"])


@pytest.mark.asyncio
async def test_finalize_needs_review():
    result = await finalize_node(_state(review_verdict="needs_review"))
    assert result["status"] == "needs_review"


@pytest.mark.asyncio
async def test_finalize_requires_explicit_review_verdict():
    """Finalize should fail fast if validate did not produce a workflow verdict."""
    with pytest.raises(ValueError, match="review_verdict"):
        await finalize_node(_state())


@pytest.mark.asyncio
async def test_validate_empty_data_all_optional():
    """Empty extraction data with only optional fields → valid."""
    result = await validate_node(
        _state(
            extracted_data={},
            schema_fields=[
                {"name": "notes", "required": False, "field_type": "string"},
                {"name": "comments", "required": False, "field_type": "string"},
            ],
        )
    )
    assert result["validation_errors"] == []
    assert result["review_verdict"] == "valid"


@pytest.mark.asyncio
async def test_validate_empty_data_with_required():
    """Empty extraction data with required fields → needs_review."""
    result = await validate_node(
        _state(
            extracted_data={},
            schema_fields=[
                {"name": "vendor", "required": True, "field_type": "string"},
            ],
        )
    )
    assert len(result["validation_errors"]) >= 1
    assert result["review_verdict"] == "needs_review"
    assert isinstance(result["validation_results"], list)
    assert any(not vr["valid"] for vr in result["validation_results"])


# ── Graph construction ──────────────────────────────────────────────


def test_graph_compiles():
    graph = build_extraction_graph()
    assert graph is not None


# ── End-to-end (with mocked providers) ──────────────────────────────


@pytest.mark.asyncio
async def test_run_extraction_full_pipeline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from app.services.llm.base import ExtractionResult

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 Invoice from Acme Corp, Total $500")

    class DummyOCR:
        async def extract_text(self, file_path: Path) -> OCRResult:
            return OCRResult(
                text="Invoice from Acme, Total $500", pages=["p1"], provider="dummy-ocr"
            )

    class DummyLLM:
        async def extract(
            self, text: str, schema_fields: list[dict], model_id: str = "auto"
        ) -> ExtractionResult:
            return ExtractionResult(
                data={"vendor": "Acme", "total": 500},
                raw_response='{"vendor":"Acme","total":500}',
                model_used="test-model",
                provider="dummy-llm",
            )

    monkeypatch.setattr(
        "app.services.ocr.registry.get_ocr_provider",
        lambda pid, *, file_path=None: DummyOCR(),
    )
    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: DummyLLM(),
    )

    result = await run_extraction(
        file_path=str(pdf),
        schema_fields=[
            {"name": "vendor", "field_type": "string", "required": True},
            {"name": "total", "field_type": "number", "required": True},
        ],
    )

    assert result["status"] == "completed"
    assert result["extracted_data"]["vendor"] == "Acme"
    assert result["ocr_provider_used"] == "dummy-ocr"
    assert result["llm_provider_used"] == "dummy-llm"
    assert result["completed_at"]
    assert result["review_verdict"] == "valid"
    assert result["validation_errors"] == []


@pytest.mark.asyncio
async def test_run_extraction_ocr_failure_skips_downstream(tmp_path: Path):
    """When parse fails the graph should short-circuit to END."""
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG")

    result = await run_extraction(
        file_path=str(img),
        schema_fields=[{"name": "x", "required": True}],
    )
    assert result["status"] == "failed"
    assert result.get("extracted_data") is None or result.get("extracted_data") == {}


@pytest.mark.asyncio
async def test_run_extraction_missing_file():
    """Non-existent file should fail at parse."""
    result = await run_extraction(
        file_path="does_not_exist.pdf",
        schema_fields=[],
    )
    assert result["status"] == "failed"
    assert "not found" in result.get("error", "").lower()


@pytest.mark.asyncio
async def test_status_values_match_enum():
    """Pipeline terminal statuses must be valid ExtractionStatus values."""
    from app.models.enums import ExtractionStatus

    valid = {s.value for s in ExtractionStatus}
    # Check all status strings used by graph nodes
    assert "ocr_complete" in valid
    assert "extracted" in valid
    assert "completed" in valid
    assert "needs_review" in valid
    assert "failed" in valid
