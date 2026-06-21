"""Pydantic v2 request/response schemas."""

from __future__ import annotations

import datetime
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    ExtractionStatus,
    FieldType,
    LLMProviderID,
    ModelCatalogSource,
    ModelSelectionMode,
    ParserEngine,
    ProviderAvailabilityState,
    ReviewDecision,
    ReviewVerdict,
)
from app.models.extraction._base import ValidationResult

# ── Schema Field definition ──────────────────────────────────────────


class SchemaFieldDef(BaseModel):
    """A single field in a user-defined extraction schema."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=100, description="Field name / key")
    description: str = Field(default="", max_length=500, description="What this field represents")
    field_type: FieldType = Field(
        default=FieldType.STRING,
        description="Expected data type",
    )
    required: bool = Field(default=True, description="Whether the field is required")


def _validate_unique_schema_fields(fields: list[SchemaFieldDef]) -> list[SchemaFieldDef]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for field in fields:
        normalized = field.name.casefold()
        original = seen.get(normalized)
        if original is not None:
            duplicates.append(field.name)
            continue
        seen[normalized] = field.name

    if duplicates:
        joined = ", ".join(sorted(set(duplicates), key=str.casefold))
        raise ValueError(f"Field names must be unique. Duplicate names: {joined}")
    return fields


# ── Extraction Schema ────────────────────────────────────────────────


class ExtractionSchemaCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    fields: list[SchemaFieldDef] = Field(..., min_length=1)

    @model_validator(mode="after")
    def validate_fields(self) -> ExtractionSchemaCreate:
        _validate_unique_schema_fields(self.fields)
        return self


class ExtractionSchemaUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    fields: list[SchemaFieldDef] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_fields(self) -> ExtractionSchemaUpdate:
        if self.fields is not None:
            _validate_unique_schema_fields(self.fields)
        return self


class ExtractionSchemaResponse(BaseModel):
    id: str
    name: str
    description: str | None
    fields: list[SchemaFieldDef]
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = {"from_attributes": True}


class SchemaPresetResponse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    id: str
    name: str
    description: str
    doc_type: str
    fields: list[SchemaFieldDef]


class CreateSchemaFromPresetRequest(BaseModel):
    """Instantiate a new schema from a built-in preset."""

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Override the preset name. Defaults to the preset name.",
    )


class LegacyCreateFromPresetRequest(CreateSchemaFromPresetRequest):
    """Deprecated compatibility payload for POST /schemas/from-preset."""

    preset_id: str = Field(..., min_length=1)


# ── Document ─────────────────────────────────────────────────────────


class DocumentResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    filename: str
    original_filename: str
    file_type: str
    file_size: int
    page_count: int | None
    status: str
    created_at: datetime.datetime


# ── Extraction ───────────────────────────────────────────────────────


class ExtractionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    document_id: str = Field(..., min_length=1, max_length=32)
    schema_id: str = Field(..., min_length=1, max_length=32)
    ocr_provider: ParserEngine = Field(
        default=ParserEngine.AUTO,
        description=(
            "User-selectable parser/OCR engine to use. Accepted values are "
            "'auto' and 'paddleocr'; internal helpers such as the built-in "
            "PyMuPDF PDF reader are not valid request values."
        ),
    )
    llm_provider: LLMProviderID = Field(
        default=LLMProviderID.AUTO,
        description=(
            "LLM provider to use. 'auto' first tries DEFAULT_LLM_PROVIDER "
            "when it is set to a concrete provider and that provider is "
            "ready, then falls back to the built-in priority order."
        ),
    )
    llm_model: str = Field(
        default="auto",
        min_length=1,
        max_length=100,
        description="LLM model id, or 'auto' to use the selected provider's default model.",
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
    ocr_provider: ParserEngine
    llm_provider: LLMProviderID
    llm_model: str
    status: ExtractionStatus
    ocr_text: str | None
    result: dict[str, Any] | None
    validation_errors: list[str] | None = None
    validation_results: list[ValidationResult] | None = None
    review_verdict: ReviewVerdict | None = None
    error: str | None
    ocr_provider_used: str | None = None
    llm_provider_used: str | None = None
    llm_model_used: str | None = None
    confidence: dict[str, float] | None = None
    extract_attempts: int | None = None
    error_category: str | None = None
    steps: list[ExtractionStepResponse] = Field(default_factory=list)
    reviews: list[ReviewResponse] = Field(default_factory=list)
    created_at: datetime.datetime
    started_at: datetime.datetime | None = None
    completed_at: datetime.datetime | None
    reviewed_at: datetime.datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("ocr_provider", mode="before")
    @classmethod
    def normalize_internal_ocr_provider(cls, value: ParserEngine | str) -> ParserEngine | str:
        """Map legacy/internal parser ids back onto the public API enum."""
        if value == "pymupdf":
            return ParserEngine.AUTO
        return value

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
        if self.review_verdict in {"approved", "corrected", "rejected"}:
            return None
        if self.validation_results is None:
            return None
        total = len(self.validation_results)
        if total == 0:
            return None
        passed = sum(1 for validation_result in self.validation_results if validation_result.valid)
        failed = total - passed
        if failed == 0:
            return f"All {total} checks passed"
        return f"{failed} of {total} checks need attention"


class ExtractionResultResponse(BaseModel):
    """Dedicated view of the extraction result (data only)."""

    extraction_id: str
    status: ExtractionStatus
    result: dict[str, Any] | None = None
    ocr_provider_used: str | None = None
    llm_provider_used: str | None = None
    llm_model_used: str | None = None
    completed_at: datetime.datetime | None = None


class ExtractionValidationResponse(BaseModel):
    """Dedicated view of the validation / review state."""

    extraction_id: str
    status: ExtractionStatus
    validation_errors: list[str]
    validation_results: list[ValidationResult] | None = None
    review_verdict: ReviewVerdict | None = None
    completed_at: datetime.datetime | None = None


# ── Review ───────────────────────────────────────────────────────────


class ReviewCreate(BaseModel):
    """Human review submission for an extraction needing review."""

    model_config = ConfigDict(str_strip_whitespace=True)

    decision: ReviewDecision = Field(..., description="approved | corrected | rejected")
    corrected_fields: dict[str, Any] | None = Field(
        default=None,
        description="New field values overriding the AI-extracted result (required when decision is corrected).",
    )
    notes: str | None = Field(default=None, max_length=2000, description="Optional reviewer notes")

    @field_validator("corrected_fields")
    @classmethod
    def validate_corrected_fields_allowed(
        cls,
        value: dict[str, Any] | None,
        info: ValidationInfo,
    ) -> dict[str, Any] | None:
        decision = info.data.get("decision")
        if value is not None and decision != ReviewDecision.CORRECTED:
            raise ValueError("corrected_fields is only allowed when decision is 'corrected'")
        return value

    @model_validator(mode="after")
    def validate_corrected_fields_required(self) -> ReviewCreate:
        if self.decision == ReviewDecision.CORRECTED and not self.corrected_fields:
            raise ValueError("corrected_fields is required when decision is 'corrected'")
        return self


class ReviewResponse(BaseModel):
    """Persisted review record."""

    id: int
    extraction_id: str
    decision: ReviewDecision
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
    # Total available OCR/parsing runtimes, including internal helpers.
    ocr_providers_available: int
    # Available parser/OCR options that a user can explicitly choose.
    user_selectable_parsers_available: int
    # Available internal parser helpers excluded from /api/providers/parsers.
    internal_parsers_available: int
    llm_providers_available: int
    supported_file_types: list[str] = Field(
        description="Accepted upload file extensions. Upload support does not mean every file type has an OCR runtime ready: PDFs use the built-in PyMuPDF text reader, while PNG/JPG/JPEG/TIFF/TIF image OCR requires PaddleOCR to be installed and enabled.",
    )
    max_upload_size_mb: int
    confidence_threshold: float


class ParserOptionInfo(BaseModel):
    """User-facing parser/OCR option with availability.

    Only user-selectable engines appear here.  Internal helpers
    (e.g. PyMuPDF) are never returned by the ``/parsers`` endpoint.
    """

    id: ParserEngine
    name: str
    enabled: bool
    available: bool


class ProviderInfo(BaseModel):
    """Deprecated legacy OCR provider shape kept for compatibility."""

    id: str
    name: str
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
    id: LLMProviderID
    name: str
    available: bool
    availability: ProviderAvailabilityStatus
    error: ProviderErrorState | None = None
    is_default: bool = False


class ModelInfo(BaseModel):
    id: str
    name: str
    provider: LLMProviderID
    is_default: bool = False


class LLMModelListResponse(BaseModel):
    provider_id: LLMProviderID
    provider_name: str
    available: bool
    source: ModelCatalogSource
    availability: ProviderAvailabilityStatus
    models: list[ModelInfo]
    error: ProviderErrorState | None = None
    resolved_provider_id: LLMProviderID | None = None


# ── App config (safe metadata for UI) ────────────────────────────────


class OCREngineFlags(BaseModel):
    """Feature flags indicating which local OCR engines are enabled."""

    paddleocr: bool = Field(
        description="Whether the optional PaddleOCR image OCR integration is enabled. This is standard image OCR, not a vision-language engine. PDFs are still handled by the built-in PyMuPDF text reader.",
    )
    glm_ocr: bool = Field(
        description="Whether the optional GLM-OCR vision-language OCR integration is enabled. GLM-OCR runs against a local Ollama server (default http://localhost:11434) and supports PNG, JPEG, and TIFF inputs.",
    )


class AppConfigResponse(BaseModel):
    """Non-secret application configuration exposed to the frontend.

    This is the single source-of-truth settings schema the UI consumes
    to build dropdowns, disable unavailable options, and show limits.
    Secret keys are never included.
    """

    parser_engines: list[ParserEngine] = Field(
        description="Ordered list of user-selectable parser engine identifiers (always includes 'auto'). Internal helpers such as the built-in PDF reader are intentionally omitted.",
    )
    llm_providers: list[LLMProviderID] = Field(
        description="Ordered list of LLM provider identifiers (always includes 'auto')",
    )
    default_llm_provider: LLMProviderID = Field(
        description="Preferred concrete provider that LLM Auto tries first when it is ready. 'auto' disables that preference and uses the built-in fallback order only.",
    )
    model_selection_modes: list[ModelSelectionMode]
    ocr_engine_flags: OCREngineFlags
    max_upload_size_mb: int
    supported_file_types: list[str] = Field(
        description="Accepted upload file extensions. Runtime parsing still depends on installed/configured parsers: PDFs use the built-in PyMuPDF reader, while PNG/JPG/JPEG/TIFF/TIF image OCR requires PaddleOCR.",
    )
    confidence_threshold: float
