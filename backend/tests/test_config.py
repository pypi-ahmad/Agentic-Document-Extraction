"""Tests for app config endpoint and enum definitions."""

import pytest
from httpx import AsyncClient

from app.models.enums import (
    ExtractionStatus,
    LLMProviderID,
    ModelCatalogSource,
    ModelSelectionMode,
    ParserEngine,
    ProviderAvailabilityState,
)

# ── Enum value stability ─────────────────────────────────────────────


def test_parser_engine_values():
    """Wire-format values must stay stable — frontend mirrors them."""
    assert ParserEngine.AUTO == "auto"
    assert ParserEngine.PADDLEOCR == "paddleocr"


def test_llm_provider_values():
    assert LLMProviderID.AUTO == "auto"
    assert LLMProviderID.OPENAI == "openai"
    assert LLMProviderID.GEMINI == "gemini"
    assert LLMProviderID.ANTHROPIC == "anthropic"


def test_extraction_status_values():
    assert ExtractionStatus.PENDING == "pending"
    assert ExtractionStatus.COMPLETED == "completed"
    assert ExtractionStatus.FAILED == "failed"


def test_model_selection_mode_values():
    assert ModelSelectionMode.AUTO == "auto"
    assert ModelSelectionMode.EXPLICIT_MODEL_ID == "explicit_model_id"


def test_provider_availability_state_values():
    assert ProviderAvailabilityState.READY == "ready"
    assert ProviderAvailabilityState.MISSING_API_KEY == "missing_api_key"
    assert ProviderAvailabilityState.INVALID_API_KEY == "invalid_api_key"


def test_model_catalog_source_values():
    assert ModelCatalogSource.DYNAMIC == "dynamic"
    assert ModelCatalogSource.PLACEHOLDER == "placeholder"


# ── /api/providers/config endpoint ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_app_config(client: AsyncClient):
    resp = await client.get("/api/providers/config")
    assert resp.status_code == 200
    data = resp.json()

    # Must include all parser engine values
    assert "auto" in data["parser_engines"]
    assert "paddleocr" in data["parser_engines"]
    assert "pymupdf" not in data["parser_engines"]

    # Must include all LLM provider values
    assert "auto" in data["llm_providers"]
    assert "openai" in data["llm_providers"]
    assert "gemini" in data["llm_providers"]
    assert "anthropic" in data["llm_providers"]

    assert data["default_llm_provider"] == "auto"

    # Model selection modes must be explicit and stable
    assert "auto" in data["model_selection_modes"]
    assert "explicit_model_id" in data["model_selection_modes"]

    # OCR feature flags must be present (booleans)
    flags = data["ocr_engine_flags"]
    assert isinstance(flags["paddleocr"], bool)

    # Upload limit must be a positive integer
    assert data["max_upload_size_mb"] > 0

    # File types must include at least pdf and png
    assert "pdf" in data["supported_file_types"]
    assert "png" in data["supported_file_types"]
    assert "jpeg" in data["supported_file_types"]
    assert "tif" in data["supported_file_types"]

    # Confidence threshold must be a valid float in range
    assert isinstance(data["confidence_threshold"], float)
    assert 0.0 <= data["confidence_threshold"] <= 1.0


@pytest.mark.asyncio
async def test_config_does_not_leak_secrets(client: AsyncClient):
    """The config endpoint must never expose API keys."""
    resp = await client.get("/api/providers/config")
    raw = resp.text.lower()
    assert "api_key" not in raw
    assert "secret" not in raw
