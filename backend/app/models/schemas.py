"""Pydantic v2 request/response schemas."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.models.enums import (
    FieldType,
    LLMProviderID,
    ModelCatalogSource,
    ModelSelectionMode,
    ParserEngine,
    ProviderAvailabilityState,
    ReviewDecision,
)


# ── Schema Field definition ──────────────────────────────────────────


class SchemaFieldDef(BaseModel):
    """A single field in a user-defined extraction schema."""

    name: str = Field(..., min_length=1, max_length=100, description="Field name / key")
    description: str = Field(
        default="", max_length=500, description="What this field represents"
    )
    field_type: FieldType = Field(
        default=FieldType.STRING,
        description="Expected data type",
    )
    required: bool = Field(default=True, description="Whether the field is required")


# ── Extraction Schema ────────────────────────────────────────────────


class ExtractionSchemaCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    fields: list[SchemaFieldDef] = Field(..., min_length=1)


class ExtractionSchemaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    fields: list[SchemaFieldDef] | None = None


class ExtractionSchemaResponse(BaseModel):
    id: str
    name: str
    description: str | None
    fields: list[SchemaFieldDef]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── Schema presets ───────────────────────────────────────────────────


class PresetFieldResponse(BaseModel):
    name: str
    description: str
    field_type: str
    required: bool


class SchemaPresetResponse(BaseModel):
    id: str
    name: str
    description: str
    doc_type: str
    fields: list[PresetFieldResponse]


class CreateFromPresetRequest(BaseModel):
    """Create a schema by copying fields from a built-in preset."""

    preset_id: str = Field(..., min_length=1)
    name: str | None = Field(
        default=None,
        max_length=255,
        description="Override the preset name. Defaults to the preset name.",
    )


# ── Document ─────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    page_count: int | None
    status: str
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── Extraction ───────────────────────────────────────────────────────


class ExtractionCreate(BaseModel):
    document_id: str = Field(..., min_length=1, max_length=32)
    schema_id: str = Field(..., min_length=1, max_length=32)
    ocr_provider: ParserEngine = Field(
        default=ParserEngine.AUTO,
        description="OCR / parser engine to use",
    )
    llm_provider: LLMProviderID = Field(
        default=LLMProviderID.AUTO,
        description="LLM provider to use",
    )
    llm_model: str = Field(
        default="auto", max_length=100, description="LLM model id, or 'auto'"
    )


class ExtractionStepResponse(BaseModel):
    """Individual pipeline step with timing."""

    name: str
    status: str
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None = None
    duration_ms: int | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class ExtractionResponse(BaseModel):
    id: str
    document_id: str
    schema_id: str
    ocr_provider: str
    llm_provider: str
    llm_model: str
    status: str
    ocr_text: str | None
    result: dict[str, Any] | None
    validation_errors: list[str] | None = None
    validation_results: list[dict[str, Any]] | None = None
    review_verdict: str | None = None
    error: str | None
    ocr_provider_used: str | None = None
    llm_provider_used: str | None = None
    llm_model_used: str | None = None
    confidence: dict[str, float] | None = None
    extract_attempts: int | None = None
    steps: list[ExtractionStepResponse] = []
    reviews: list[ReviewResponse] = []
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def duration_total_ms(self) -> int | None:
        """Wall-clock milliseconds from pipeline start to completion."""
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def validation_summary(self) -> str | None:
        """Human-friendly one-liner summarising validation state."""
        if self.validation_results is None:
            return None
        total = len(self.validation_results)
        if total == 0:
            return None
        passed = sum(1 for v in self.validation_results if v.get("valid"))
        failed = total - passed
        if failed == 0:
            return f"All {total} checks passed"
        return f"{failed} of {total} checks need attention"


class ExtractionResultResponse(BaseModel):
    """Dedicated view of the extraction result (data only)."""

    extraction_id: str
    status: str
    result: dict[str, Any] | None = None
    ocr_provider_used: str | None = None
    llm_provider_used: str | None = None
    llm_model_used: str | None = None
    completed_at: datetime.datetime | None = None


class ExtractionValidationResponse(BaseModel):
    """Dedicated view of the validation / review state."""

    extraction_id: str
    status: str
    validation_errors: list[str]
    validation_results: list[dict[str, Any]] | None = None
    review_verdict: str | None = None
    completed_at: datetime.datetime | None = None


# ── Review ───────────────────────────────────────────────────────────


class ReviewCreate(BaseModel):
    """Human review submission for an extraction needing review."""

    decision: ReviewDecision = Field(
        ..., description="approved | corrected | rejected"
    )
    corrected_fields: dict[str, Any] | None = Field(
        default=None,
        description="New field values overriding the AI-extracted result (required when decision is corrected).",
    )
    notes: str | None = Field(
        default=None, max_length=2000, description="Optional reviewer notes"
    )


class ReviewResponse(BaseModel):
    """Persisted review record."""

    id: int
    extraction_id: str
    decision: str
    corrected_fields: dict[str, Any] | None = None
    notes: str | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


# ── App info ─────────────────────────────────────────────────────────


class AppInfoResponse(BaseModel):
    """Runtime capabilities and version info for the frontend."""

    app_name: str
    version: str
    python_version: str
    langgraph_version: str | None = None
    pipeline_nodes: list[str]
    ocr_providers_available: int
    llm_providers_available: int
    supported_file_types: list[str]
    max_upload_size_mb: int


# ── Provider info ────────────────────────────────────────────────────


class ProviderInfo(BaseModel):
    id: str
    name: str
    available: bool = True


class ParserOptionInfo(BaseModel):
    """User-facing parser/OCR option with availability.

    Only user-selectable engines appear here.  Internal helpers
    (e.g. PyMuPDF) are never returned by the ``/parsers`` endpoint.
    """

    id: str
    name: str
    enabled: bool
    available: bool


class ProviderErrorState(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ProviderAvailabilityStatus(BaseModel):
    state: ProviderAvailabilityState
    configured: bool
    available: bool
    can_extract: bool
    can_list_models: bool
    auto_eligible: bool


class LLMProviderInfo(BaseModel):
    id: str
    name: str
    available: bool
    availability: ProviderAvailabilityStatus
    error: ProviderErrorState | None = None
    is_default: bool = False


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    is_default: bool = False


class LLMModelListResponse(BaseModel):
    provider_id: str
    provider_name: str
    available: bool
    source: ModelCatalogSource
    availability: ProviderAvailabilityStatus
    models: list[ModelInfo]
    error: ProviderErrorState | None = None
    resolved_provider_id: str | None = None


# ── App config (safe metadata for UI) ────────────────────────────────


class OCREngineFlags(BaseModel):
    """Feature flags indicating which local OCR engines are enabled."""

    paddleocr: bool


class AppConfigResponse(BaseModel):
    """Non-secret application configuration exposed to the frontend.

    This is the single source-of-truth settings schema the UI consumes
    to build dropdowns, disable unavailable options, and show limits.
    Secret keys are never included.
    """

    parser_engines: list[ParserEngine] = Field(
        description="Ordered list of parser engine identifiers (always includes 'auto')",
    )
    llm_providers: list[LLMProviderID] = Field(
        description="Ordered list of LLM provider identifiers (always includes 'auto')",
    )
    default_llm_provider: LLMProviderID
    model_selection_modes: list[ModelSelectionMode]
    ocr_engine_flags: OCREngineFlags
    max_upload_size_mb: int
    supported_file_types: list[str]
