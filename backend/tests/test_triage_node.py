"""Tests for the triage node that selects the OCR/parser engine.

Covers the policy rules:

- PDFs route to docling.
- Images route to glmocr.
- Office docs and HTML route to docling.
- Unknown suffixes fall through to the default auto path.
- An explicit ``ocr_provider_id`` selection is honored and the
  triage decision reflects that.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.extraction.graph import PipelineState, triage_node


def _state(**overrides: Any) -> PipelineState:
    base: PipelineState = {
        "file_path": "x.pdf",
        "schema_fields": [],
        "ocr_provider_id": "auto",
        "llm_provider_id": "auto",
        "llm_model_id": "auto",
    }
    base.update(overrides)
    return base


# ── PDF ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_triage_pdf_prefers_docling() -> None:
    out = await triage_node(_state(file_path="report.pdf"))
    assert out["triage_engine"] == "docling"
    assert "layout" in out["triage_reason"].lower() or "table" in out["triage_reason"].lower()


# ── Image ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_triage_png_prefers_glmocr() -> None:
    out = await triage_node(_state(file_path="receipt.png"))
    assert out["triage_engine"] == "glmocr"


@pytest.mark.asyncio
async def test_triage_jpeg_prefers_glmocr() -> None:
    out = await triage_node(_state(file_path="scan.jpeg"))
    assert out["triage_engine"] == "glmocr"


@pytest.mark.asyncio
async def test_triage_tiff_prefers_glmocr() -> None:
    out = await triage_node(_state(file_path="archive.tif"))
    assert out["triage_engine"] == "glmocr"


# ── Office / HTML ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_triage_docx_prefers_docling() -> None:
    out = await triage_node(_state(file_path="contract.docx"))
    assert out["triage_engine"] == "docling"


@pytest.mark.asyncio
async def test_triage_html_prefers_docling() -> None:
    out = await triage_node(_state(file_path="page.html"))
    assert out["triage_engine"] == "docling"


# ── Unknown ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_triage_unknown_falls_through() -> None:
    out = await triage_node(_state(file_path="data.xyz"))
    assert out["triage_engine"] == "auto"
    assert out["triage_decision"] == "auto_default"


# ── Honor caller ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_triage_honors_explicit_caller() -> None:
    out = await triage_node(_state(file_path="x.pdf", ocr_provider_id="paddleocr"))
    assert out["triage_decision"] == "honor_caller"
    assert out["triage_engine"] == "paddleocr"


@pytest.mark.asyncio
async def test_triage_missing_file_path_is_safe() -> None:
    """When file_path is empty, the triage still returns a valid
    decision (no rule matches; falls through to default)."""
    out = await triage_node(_state(file_path=""))
    assert "triage_decision" in out
    assert "triage_engine" in out
    assert "triage_reason" in out
