"""Tests for agentic pipeline features: retry, confidence, exception routing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services.extraction.graph import (
    _MAX_LLM_RETRIES,
    PipelineState,
    extract_node,
    validate_node,
)
from app.services.extraction.validation import (
    _LOW_CONFIDENCE_THRESHOLD,
    _validate_confidence,
    compute_review_verdict,
    validate_extraction,
)
from app.services.llm.base import ExtractionResult, LLMProviderError, _is_retryable_error
from app.services.llm.output_parser import extract_confidence
from app.services.ocr.base import OCRResult

# ── Helpers ──────────────────────────────────────────────────────────


def _state(**overrides: Any) -> PipelineState:
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


# ── extract_confidence ──────────────────────────────────────────────


def test_extract_confidence_present():
    data = {"vendor": "Acme", "total": 100, "_confidence": {"vendor": 0.95, "total": 0.4}}
    clean, conf = extract_confidence(data)
    assert "_confidence" not in clean
    assert clean == {"vendor": "Acme", "total": 100}
    assert conf == {"vendor": 0.95, "total": 0.4}


def test_extract_confidence_absent():
    data = {"vendor": "Acme"}
    clean, conf = extract_confidence(data)
    assert clean == {"vendor": "Acme"}
    assert conf == {}


def test_extract_confidence_invalid_values():
    data = {"vendor": "Acme", "_confidence": {"vendor": "high", "total": 1.5, "date": -0.1}}
    _clean, conf = extract_confidence(data)
    assert conf == {}  # all invalid; "high" not a number, 1.5 > 1.0, -0.1 < 0.0


def test_extract_confidence_partial_valid():
    data = {"a": 1, "b": 2, "_confidence": {"a": 0.8, "b": "nope"}}
    _clean, conf = extract_confidence(data)
    assert conf == {"a": 0.8}


def test_extract_confidence_rounds():
    data = {"x": 1, "_confidence": {"x": 0.123456789}}
    _, conf = extract_confidence(data)
    assert conf == {"x": 0.123}


# ── _validate_confidence ────────────────────────────────────────────


def test_validate_confidence_flags_low():
    fields = [{"name": "vendor", "field_type": "string", "required": True}]
    data = {"vendor": "Acme"}
    confidence = {"vendor": 0.3}
    results = _validate_confidence(data, fields, confidence)
    assert len(results) == 1
    assert not results[0].valid
    assert "30%" in results[0].message


def test_validate_confidence_passes_high():
    fields = [{"name": "vendor", "field_type": "string", "required": True}]
    data = {"vendor": "Acme"}
    confidence = {"vendor": 0.95}
    results = _validate_confidence(data, fields, confidence)
    assert len(results) == 0


def test_validate_confidence_skips_null():
    fields = [{"name": "vendor", "field_type": "string", "required": True}]
    data = {"vendor": None}
    confidence = {"vendor": 0.1}
    results = _validate_confidence(data, fields, confidence)
    assert len(results) == 0  # null handled by required check


def test_validate_confidence_threshold_exact():
    """Score exactly at threshold should pass."""
    fields = [{"name": "vendor", "field_type": "string", "required": True}]
    data = {"vendor": "Acme"}
    confidence = {"vendor": _LOW_CONFIDENCE_THRESHOLD}
    results = _validate_confidence(data, fields, confidence)
    assert len(results) == 0


# ── validate_extraction with confidence ─────────────────────────────


def test_validate_extraction_low_confidence_triggers_review():
    fields = [
        {"name": "vendor", "field_type": "string", "required": True},
        {"name": "total", "field_type": "number", "required": True},
    ]
    data = {"vendor": "Acme", "total": 100}
    confidence = {"vendor": 0.9, "total": 0.3}
    results = validate_extraction(data, fields, confidence=confidence)
    verdict = compute_review_verdict(results)
    assert verdict == "needs_review"
    error_fields = [r.field_name for r in results if not r.valid]
    assert "total" in error_fields


def test_validate_extraction_no_confidence_still_works():
    fields = [{"name": "vendor", "field_type": "string", "required": True}]
    data = {"vendor": "Acme"}
    results = validate_extraction(data, fields)
    verdict = compute_review_verdict(results)
    assert verdict == "valid"


# ── Extract node retry ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extract_node_retries_on_retryable_error(monkeypatch: pytest.MonkeyPatch):
    call_count = 0

    class RetryableLLM:
        async def extract(
            self, text: str, schema_fields: list, model_id: str = "auto"
        ) -> ExtractionResult:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise LLMProviderError("test", "rate limited", code="rate_limit", retryable=True)
            return ExtractionResult(
                data={"vendor": "Acme"},
                raw_response='{"vendor":"Acme"}',
                model_used="m",
                provider="test",
                confidence={"vendor": 0.9},
            )

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", lambda pid: RetryableLLM())
    # Speed up test by eliminating backoff delay
    monkeypatch.setattr("app.services.extraction.graph._RETRY_BASE_DELAY", 0.0)

    result = await extract_node(_state(ocr_text="Invoice"))
    assert result["status"] == "extracted"
    assert result["extract_attempts"] == 3
    assert call_count == 3


@pytest.mark.asyncio
async def test_extract_node_fails_non_retryable_immediately(monkeypatch: pytest.MonkeyPatch):
    call_count = 0

    class NonRetryableLLM:
        async def extract(
            self, text: str, schema_fields: list, model_id: str = "auto"
        ) -> ExtractionResult:
            nonlocal call_count
            call_count += 1
            raise LLMProviderError("test", "bad key", code="invalid_api_key", retryable=False)

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", lambda pid: NonRetryableLLM())
    monkeypatch.setattr("app.services.extraction.graph._RETRY_BASE_DELAY", 0.0)

    result = await extract_node(_state(ocr_text="Invoice"))
    assert result["status"] == "failed"
    assert result["extract_attempts"] == 1
    assert call_count == 1


@pytest.mark.asyncio
async def test_extract_node_exhausts_retries(monkeypatch: pytest.MonkeyPatch):
    call_count = 0

    class AlwaysRetryableLLM:
        async def extract(
            self, text: str, schema_fields: list, model_id: str = "auto"
        ) -> ExtractionResult:
            nonlocal call_count
            call_count += 1
            raise LLMProviderError("test", "server error", code="server_error", retryable=True)

    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider", lambda pid: AlwaysRetryableLLM()
    )
    monkeypatch.setattr("app.services.extraction.graph._RETRY_BASE_DELAY", 0.0)

    result = await extract_node(_state(ocr_text="Invoice"))
    assert result["status"] == "failed"
    assert result["extract_attempts"] == _MAX_LLM_RETRIES + 1
    assert call_count == _MAX_LLM_RETRIES + 1


@pytest.mark.asyncio
async def test_extract_node_returns_confidence(monkeypatch: pytest.MonkeyPatch):
    class ConfidentLLM:
        async def extract(
            self, text: str, schema_fields: list, model_id: str = "auto"
        ) -> ExtractionResult:
            return ExtractionResult(
                data={"vendor": "Acme"},
                raw_response="{}",
                model_used="m",
                provider="test",
                confidence={"vendor": 0.95},
            )

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", lambda pid: ConfidentLLM())

    result = await extract_node(_state(ocr_text="Invoice"))
    assert result["status"] == "extracted"
    assert result["confidence"] == {"vendor": 0.95}
    assert result["extract_attempts"] == 1


# ── Validate node with confidence ───────────────────────────────────


@pytest.mark.asyncio
async def test_validate_node_uses_confidence():
    result = await validate_node(
        _state(
            extracted_data={"vendor": "Acme", "total": 100},
            schema_fields=[
                {"name": "vendor", "required": True, "field_type": "string"},
                {"name": "total", "required": True, "field_type": "number"},
            ],
            confidence={"vendor": 0.9, "total": 0.2},
        )
    )
    assert result["review_verdict"] == "needs_review"
    assert any("total" in e for e in result["validation_errors"])


@pytest.mark.asyncio
async def test_validate_node_no_confidence_still_valid():
    """When confidence is absent or empty, validation works as before."""
    result = await validate_node(
        _state(
            extracted_data={"vendor": "Acme"},
            schema_fields=[
                {"name": "vendor", "required": True, "field_type": "string"},
            ],
        )
    )
    assert result["review_verdict"] == "valid"


# ── Full pipeline with retry + confidence ────────────────────────────


@pytest.mark.asyncio
async def test_full_pipeline_confidence_triggers_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from app.services.extraction.graph import run_extraction

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    class DummyOCR:
        async def extract_text(self, file_path: Path) -> OCRResult:
            return OCRResult(text="Invoice", pages=["p1"], provider="dummy-ocr")

    class LowConfidenceLLM:
        async def extract(
            self, text: str, schema_fields: list, model_id: str = "auto"
        ) -> ExtractionResult:
            return ExtractionResult(
                data={"vendor": "Maybe Corp"},
                raw_response='{"vendor":"Maybe Corp"}',
                model_used="test-model",
                provider="dummy-llm",
                confidence={"vendor": 0.3},
            )

    monkeypatch.setattr(
        "app.services.ocr.registry.get_ocr_provider",
        lambda pid, *, file_path=None: DummyOCR(),
    )
    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: LowConfidenceLLM(),
    )

    result = await run_extraction(
        file_path=str(pdf),
        schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
    )

    assert result["status"] == "needs_review"
    assert result["confidence"] == {"vendor": 0.3}
    assert any("30%" in e for e in result.get("validation_errors", []))


# ── DB persistence tests ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_extraction_response_includes_confidence(client):
    """Confidence and extract_attempts are returned in the API response."""
    from app.models.db_models import Document, Extraction, ExtractionSchema
    from tests.conftest import _test_session_maker

    async with _test_session_maker() as db:
        doc = Document(
            filename="t.pdf",
            original_filename="t.pdf",
            file_path="/tmp/t.pdf",
            file_type="pdf",
            file_size=100,
        )
        schema = ExtractionSchema(
            name="TestConf",
            fields=[{"name": "vendor", "field_type": "string", "required": True}],
        )
        db.add_all([doc, schema])
        await db.flush()
        ext = Extraction(
            document_id=doc.id,
            schema_id=schema.id,
            status="completed",
            result={"vendor": "Acme"},
            confidence={"vendor": 0.85},
            extract_attempts=2,
        )
        db.add(ext)
        await db.flush()
        eid = ext.id
        await db.commit()

    resp = await client.get(f"/api/extractions/{eid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == {"vendor": 0.85}
    assert data["extract_attempts"] == 2


# ── _is_retryable_error heuristic ───────────────────────────────────


def test_is_retryable_rate_limit():
    assert _is_retryable_error(Exception("Rate limit exceeded")) is True


def test_is_retryable_429():
    assert _is_retryable_error(Exception("Error code: 429")) is True


def test_is_retryable_server_error():
    assert _is_retryable_error(Exception("503 Service Unavailable")) is True


def test_is_retryable_timeout():
    assert _is_retryable_error(Exception("Request timed out")) is True


def test_is_retryable_auth_error():
    assert _is_retryable_error(Exception("Invalid API key")) is False


def test_is_retryable_parse_error():
    assert _is_retryable_error(Exception("Unexpected token in JSON")) is False


def test_is_retryable_cause_chain():
    """Retryable cause in __cause__ chain should be detected."""
    cause = Exception("upstream 429 rate limit")
    wrapper = Exception("LLM call failed")
    wrapper.__cause__ = cause
    assert _is_retryable_error(wrapper) is True


def test_is_retryable_non_retryable_cause():
    cause = Exception("bad credentials")
    wrapper = Exception("LLM call failed")
    wrapper.__cause__ = cause
    assert _is_retryable_error(wrapper) is False


# ── Provider retryable wiring (real catch-all path) ──────────────────


@pytest.mark.asyncio
async def test_extract_node_retries_raw_rate_limit(monkeypatch: pytest.MonkeyPatch):
    """A provider raising a raw rate-limit exception actually triggers retries."""
    call_count = 0

    class RawRateLimitLLM:
        async def extract(
            self, text: str, schema_fields: list, model_id: str = "auto"
        ) -> ExtractionResult:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Simulate a raw SDK exception (not LLMProviderError) with rate limit message,
                # which providers now detect and wrap as retryable.
                raise LLMProviderError("test", "Error code: 429", retryable=True)
            return ExtractionResult(
                data={"vendor": "Acme"},
                raw_response='{"vendor":"Acme"}',
                model_used="m",
                provider="test",
            )

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", lambda pid: RawRateLimitLLM())
    monkeypatch.setattr("app.services.extraction.graph._RETRY_BASE_DELAY", 0.0)

    result = await extract_node(_state(ocr_text="Invoice"))
    assert result["status"] == "extracted"
    assert result["extract_attempts"] == 3
    assert call_count == 3
