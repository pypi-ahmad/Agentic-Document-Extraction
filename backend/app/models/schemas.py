"""Public request and response schemas for document parse jobs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.parsing.quality_policy import QualityOverrides


class ExtractionSchemaWrite(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    json_schema: dict[str, Any]


class ExtractionSchemaValidateRequest(BaseModel):
    json_schema: dict[str, Any]


class ExtractionSchemaValidationError(BaseModel):
    path: str
    code: str
    message: str


class ExtractionSchemaValidationResponse(BaseModel):
    valid: bool
    normalized_schema: dict[str, Any] | None = None
    errors: list[ExtractionSchemaValidationError] = Field(default_factory=list)


class ExtractionSchemaResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    version: int
    json_schema: dict[str, Any]
    schema_sha256: str
    created_at: str | None = None
    updated_at: str | None = None


class ExtractionSchemaListResponse(BaseModel):
    items: list[ExtractionSchemaResponse]


class ParseSettings(BaseModel):
    segment_documents: bool = True
    document_profile: Literal[
        "auto",
        "technical_document",
        "scientific_paper",
        "invoice",
        "insurance_claim",
        "healthcare_form",
        "general_scanned",
    ] = "auto"
    structured_extraction: bool = True
    extraction_schema_id: str | None = Field(default=None, min_length=1, max_length=32)
    extraction_provider: Literal["ollama", "openai", "anthropic", "gemini", "xai"] = "ollama"
    extraction_model: str | None = Field(default=None, min_length=1, max_length=120)
    allow_sensitive_cloud: bool = False
    processing_mode: Literal["local_only", "hybrid", "maximum_accuracy"] = "local_only"
    quality_overrides: QualityOverrides = Field(default_factory=QualityOverrides)
    ocr_provider: Literal["openai", "anthropic", "gemini", "xai", "glmocr"] = "glmocr"
    ocr_model: str | None = Field(default=None, min_length=1, max_length=120)
    review_provider: Literal["ollama", "openai", "anthropic", "gemini", "xai"] = "ollama"
    review_model: str | None = Field(default=None, min_length=1, max_length=120)
    cloud_mode: Literal["off", "adaptive", "all_pages"] = "off"
    blind_local_retry: bool = False
    start_page: int = Field(default=1, ge=1)
    end_page: int | None = Field(default=None, ge=1)
    input_mode: Literal["scanned", "native", "mixed"] = "mixed"
    dpi: Literal[150, 200, 300] = 200
    layout_device: Literal["auto", "cpu", "cuda"] = "auto"
    region_concurrency: int = Field(default=2, ge=1, le=8)
    marginalia_policy: Literal["remove_repeated", "keep_all"] = "remove_repeated"
    describe_figures: bool = True
    grounding_pdf: bool = Field(
        default=True,
        description="Deprecated compatibility flag; annotated PDF generation is always enabled.",
        json_schema_extra={"deprecated": True},
    )
    searchable_pdf: bool = True
    bundle: bool = True

    @model_validator(mode="before")
    @classmethod
    def infer_legacy_cloud_mode(cls, data: Any) -> Any:
        if isinstance(data, dict):
            normalized: dict[str, Any] = {str(key): value for key, value in data.items()}
            if "cloud_mode" not in normalized and normalized.get("review_model"):
                normalized["cloud_mode"] = "adaptive"
            if "processing_mode" not in normalized:
                cloud_mode = normalized.get("cloud_mode")
                normalized["processing_mode"] = {
                    "adaptive": "hybrid",
                    "all_pages": "maximum_accuracy",
                }.get(cloud_mode if isinstance(cloud_mode, str) else "", "local_only")
            return normalized
        return data

    @model_validator(mode="after")
    def validate_page_range(self) -> ParseSettings:
        if self.end_page is not None and self.end_page < self.start_page:
            raise ValueError("end_page must be greater than or equal to start_page")
        self.grounding_pdf = True
        if self.processing_mode == "local_only":
            self.cloud_mode = "off"
            self.blind_local_retry = False
        elif self.processing_mode == "hybrid":
            self.cloud_mode = "adaptive"
        else:
            self.cloud_mode = "all_pages"
        if self.review_provider != "ollama" and not self.review_model:
            raise ValueError("review_model is required for a cloud review provider")
        if self.cloud_mode != "off" and not self.review_model:
            raise ValueError("review_model is required when cloud context is enabled")
        if self.extraction_schema_id and not self.extraction_model:
            raise ValueError("extraction_model is required when an extraction schema is selected")
        if (
            self.extraction_schema_id
            and self.processing_mode == "local_only"
            and self.extraction_provider != "ollama"
        ):
            raise ValueError("local_only schema extraction requires an Ollama model")
        if (
            self.document_profile in {"insurance_claim", "healthcare_form"}
            and (
                self.cloud_mode != "off"
                or (self.extraction_schema_id and self.extraction_provider != "ollama")
            )
            and not self.allow_sensitive_cloud
        ):
            raise ValueError(
                "allow_sensitive_cloud must be enabled before a sensitive document can use cloud models"
            )
        return self


class PageCheckpointResponse(BaseModel):
    page_number: int
    status: str
    routing: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    attempts: int
    duration_ms: float | None = None
    stage: str | None = None
    quality_status: str | None = None
    quality_score: float | None = None
    repair_count: int = 0
    diagnostics_url: str | None = None


class ArtifactResponse(BaseModel):
    id: str
    type: str
    region_id: str | None = None
    mime_type: str
    size: int
    sha256: str
    filename: str
    download_url: str
    preview_url: str | None = None


class SubDocumentSummary(BaseModel):
    id: str
    ordinal: int
    start_page: int
    end_page: int
    profile: str
    confidence: float
    identifiers: list[dict[str, Any]] = Field(default_factory=list)
    boundary_confidence: float
    boundary_reasons: list[str] = Field(default_factory=list)
    complete: bool
    missing_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)


class SubDocumentListResponse(BaseModel):
    items: list[SubDocumentSummary]


class ExtractionSchemaSnapshotSummary(BaseModel):
    id: str
    name: str
    version: int
    schema_sha256: str


class ParseJobResponse(BaseModel):
    id: str
    batch_id: str | None = None
    batch_ordinal: int | None = None
    original_filename: str
    source_mime: str
    source_size: int
    source_sha256: str
    page_count: int
    status: str
    settings: ParseSettings
    quality_policy: dict[str, Any] | None = None
    current_page: int | None = None
    current_batch: int | None = None
    total_batches: int = 1
    detected_profile: str | None = None
    profile_confidence: float | None = None
    segmentation_status: str = "not_run"
    subdocument_count: int = 0
    is_partial: bool = False
    completed_pages: int
    failed_pages: int
    warning_count: int
    review_required_count: int = 0
    source_preview_url: str
    output_revision: int = 1
    verified_export_ready: bool = False
    error_code: str | None = None
    error_message: str | None = None
    model_name: str | None = None
    model_digest: str | None = None
    review_model_name: str | None = None
    review_model_digest: str | None = None
    extraction_schema: ExtractionSchemaSnapshotSummary | None = None
    extraction_model_name: str | None = None
    extraction_model_digest: str | None = None
    created_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    pages: list[PageCheckpointResponse] = Field(default_factory=list)
    artifacts: list[ArtifactResponse] = Field(default_factory=list)


class ParseJobListResponse(BaseModel):
    items: list[ParseJobResponse]
    total: int
    offset: int
    limit: int
