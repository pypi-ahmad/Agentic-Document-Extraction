"""Tests for the reflection loop in the extraction graph.

Covers:

- The reflection prompt builder.
- The reflect_node behavior (skips when valid, no-ops when cap reached,
  re-invokes the LLM on validation failure).
- The full graph wiring: validate → reflect → validate/finalize.
- The ``reflection_attempts`` and ``reflection_history`` state fields.
- End-to-end: a bad first extraction is corrected by the reflection pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.config import settings
from app.services.extraction.graph import (
    PipelineState,
    build_extraction_graph,
    finalize_node,
    reflect_node,
    run_extraction,
    validate_node,
)


def _state(**overrides: Any) -> PipelineState:
    base: PipelineState = {
        "file_path": "sample.pdf",
        "schema_fields": [],
        "ocr_provider_id": "auto",
        "llm_provider_id": "auto",
        "llm_model_id": "auto",
        "status": "extracted",
    }
    base.update(overrides)
    return base


# ── Reflect node: happy path ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_node_skips_when_valid():
    """No-op when the previous validation passed."""
    result = await reflect_node(_state(review_verdict="valid", validation_errors=[]))
    assert result == {}


# ── Reflect node: cap reached ────────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_node_no_op_when_cap_reached(monkeypatch):
    """No-op when reflection_attempts >= max_reflection_attempts."""
    called: list[Any] = []

    def _fail(*_args: Any, **_kwargs: Any) -> None:
        called.append(True)
        raise AssertionError("LLM should not be called when cap is reached")

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", _fail)

    state = _state(
        review_verdict="needs_review",
        validation_errors=["missing total"],
        reflection_attempts=settings.max_reflection_attempts,
    )
    result = await reflect_node(state)
    assert result == {}
    assert called == []


@pytest.mark.asyncio
async def test_reflect_node_disabled_when_max_is_zero(monkeypatch):
    """max_reflection_attempts=0 disables the loop entirely."""
    called: list[Any] = []

    def _fail(*_args: Any, **_kwargs: Any) -> None:
        called.append(True)

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", _fail)
    monkeypatch.setattr(settings, "max_reflection_attempts", 0)

    state = _state(
        review_verdict="needs_review",
        validation_errors=["missing total"],
        reflection_attempts=0,
    )
    result = await reflect_node(state)
    assert result == {}
    assert called == []


# ── Reflect node: re-invokes LLM ─────────────────────────────────────


@pytest.mark.asyncio
async def test_reflect_node_calls_llm_on_needs_review(monkeypatch):
    """On a failed validation, the reflect node re-invokes the LLM with
    a reflection prompt that includes the previous data and errors."""
    from app.services.llm.base import ExtractionResult

    captured: dict[str, Any] = {}

    class DummyLLM:
        async def extract(
            self, text: str, schema_fields: list[dict], model_id: str = "auto"
        ) -> ExtractionResult:
            captured["text"] = text
            captured["schema_fields"] = schema_fields
            return ExtractionResult(
                data={"vendor": "Acme", "total": 500},
                raw_response='{"vendor":"Acme","total":500}',
                model_used="test-model",
                provider="dummy-llm",
                confidence={"vendor": 0.95, "total": 0.95},
            )

    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: DummyLLM(),
    )

    state = _state(
        review_verdict="needs_review",
        validation_errors=["missing total"],
        extracted_data={"vendor": "Acme"},
        confidence={"vendor": 0.9, "total": 0.0},
        ocr_text="Invoice from Acme, Total $500",
        schema_fields=[
            {"name": "vendor", "field_type": "string", "required": True},
            {"name": "total", "field_type": "number", "required": True},
        ],
    )
    result = await reflect_node(state)
    assert result["status"] == "extracted"
    assert result["extracted_data"]["total"] == 500
    assert result["reflection_attempts"] == 1
    assert len(result["reflection_history"]) == 1
    assert result["reflection_history"][0]["attempt"] == 1
    # The reflection prompt should contain the previous data and errors.
    assert "Acme" in captured["text"]
    assert "missing total" in captured["text"]
    assert "REFLECTION ATTEMPT: 1" in captured["text"]


@pytest.mark.asyncio
async def test_reflect_node_handles_llm_failure(monkeypatch):
    """When the reflection LLM call itself fails, we fall back to
    finalize with the previous verdict (do not crash the pipeline)."""
    from app.services.llm.base import LLMProviderError

    def raise_error(pid: str):
        raise LLMProviderError("test", "boom", code="provider_error")

    monkeypatch.setattr("app.services.llm.registry.get_llm_provider", raise_error)

    state = _state(
        review_verdict="needs_review",
        validation_errors=["missing total"],
        extracted_data={"vendor": "Acme"},
        ocr_text="Invoice from Acme",
        schema_fields=[{"name": "vendor", "required": True}],
    )
    result = await reflect_node(state)
    assert result == {}


# ── State fields are present ─────────────────────────────────────────


def test_pipeline_state_has_reflection_fields():
    from app.services.extraction.graph import PipelineState

    annotations = PipelineState.__annotations__
    assert "reflection_attempts" in annotations
    assert "reflection_history" in annotations


# ── End-to-end: graph routes through reflect ────────────────────────


@pytest.mark.asyncio
async def test_graph_uses_reflect_in_path(tmp_path: Path, monkeypatch):
    """A bad first extraction is corrected by a reflection pass."""
    from app.services.llm.base import ExtractionResult

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    class DummyOCR:
        async def extract_text(self, file_path: Path):
            from app.services.ocr.base import OCRResult

            return OCRResult(
                text="Invoice from Acme, Total $500", pages=["p1"], provider="dummy-ocr"
            )

    # The first LLM call returns a partial extraction; the second
    # (reflection) call returns a corrected one.
    call_count = {"n": 0}

    class DummyLLM:
        async def extract(
            self, text: str, schema_fields: list[dict], model_id: str = "auto"
        ) -> ExtractionResult:
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: missing required 'total'.
                return ExtractionResult(
                    data={"vendor": "Acme"},
                    raw_response='{"vendor":"Acme"}',
                    model_used="m",
                    provider="dummy-llm",
                    confidence={"vendor": 0.9, "total": 0.0},
                )
            # Reflection call: corrected.
            return ExtractionResult(
                data={"vendor": "Acme", "total": 500},
                raw_response='{"vendor":"Acme","total":500}',
                model_used="m",
                provider="dummy-llm",
                confidence={"vendor": 0.9, "total": 0.95},
            )

    monkeypatch.setattr(
        "app.services.ocr.registry.get_ocr_provider",
        lambda pid, *, file_path=None: DummyOCR(),
    )
    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: DummyLLM(),
    )

    graph = build_extraction_graph()
    from app.services.extraction.graph import build_initial_state

    result = await graph.ainvoke(
        build_initial_state(
            file_path=str(pdf),
            schema_fields=[
                {"name": "vendor", "field_type": "string", "required": True},
                {"name": "total", "field_type": "number", "required": True},
            ],
        )
    )
    assert result["status"] == "completed"
    assert result["extracted_data"]["total"] == 500
    assert result["review_verdict"] == "valid"
    assert result["reflection_attempts"] == 1
    assert len(result["reflection_history"]) == 1
    # Two LLM calls: initial + one reflection.
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_graph_caps_reflection_at_max(monkeypatch, tmp_path: Path):
    """Even when the reflection never converges, the pipeline stops after
    max_reflection_attempts and routes to finalize with needs_review."""
    from app.services.extraction.graph import build_initial_state
    from app.services.llm.base import ExtractionResult

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")

    class DummyOCR:
        async def extract_text(self, file_path: Path):
            from app.services.ocr.base import OCRResult

            return OCRResult(text="text", pages=["p1"], provider="dummy-ocr")

    class DummyLLM:
        async def extract(
            self, text: str, schema_fields: list[dict], model_id: str = "auto"
        ) -> ExtractionResult:
            # Always return a partial extraction.
            return ExtractionResult(
                data={"vendor": "Acme"},  # missing 'total'
                raw_response='{"vendor":"Acme"}',
                model_used="m",
                provider="dummy-llm",
                confidence={"vendor": 0.9, "total": 0.0},
            )

    monkeypatch.setattr(
        "app.services.ocr.registry.get_ocr_provider",
        lambda pid, *, file_path=None: DummyOCR(),
    )
    monkeypatch.setattr(
        "app.services.llm.registry.get_llm_provider",
        lambda pid: DummyLLM(),
    )

    graph = build_extraction_graph()
    result = await graph.ainvoke(
        build_initial_state(
            file_path=str(pdf),
            schema_fields=[
                {"name": "vendor", "field_type": "string", "required": True},
                {"name": "total", "field_type": "number", "required": True},
            ],
        )
    )
    # Status is needs_review because we never satisfied 'total'.
    assert result["status"] == "needs_review"
    # We attempted reflection exactly max_reflection_attempts times.
    assert result["reflection_attempts"] == settings.max_reflection_attempts


# ── Sanity: validate still works with the new state fields ───────────


@pytest.mark.asyncio
async def test_validate_node_unchanged():
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


@pytest.mark.asyncio
async def test_finalize_node_unchanged():
    result = await finalize_node(_state(review_verdict="valid"))
    assert result["status"] == "completed"


# ── run_extraction still works end-to-end ────────────────────────────


@pytest.mark.asyncio
async def test_run_extraction_happy_path_unchanged(tmp_path: Path, monkeypatch):
    """The existing run_extraction behavior is preserved when no
    reflection is needed (validation passes on the first try)."""
    from app.services.llm.base import ExtractionResult

    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 Invoice from Acme Corp, Total $500")

    class DummyOCR:
        async def extract_text(self, file_path: Path):
            from app.services.ocr.base import OCRResult

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
    assert result["reflection_attempts"] == 0
    assert result["extracted_data"]["total"] == 500
