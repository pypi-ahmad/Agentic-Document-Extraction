"""Typed contracts shared by the local agentic parsing stages."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.parsing.contracts import BoundingBox, RegionSource, RegionType


class PlanningMode(StrEnum):
    PAGE_CENTRIC = "page_centric"
    TWO_PASS_DOCUMENT = "two_pass_document"


class ProcessingStrategy(StrEnum):
    NATIVE = "native"
    OCR = "ocr"
    SPECIALIST = "specialist"
    FALLBACK = "fallback"


class ExpertKind(StrEnum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    FIGURE = "figure"
    FORMULA = "formula"
    FALLBACK = "fallback"


class QualityStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class VerificationMethod(StrEnum):
    LOCAL_COORDINATE = "local_coordinate"
    CLOUD_VISUAL = "cloud_visual"


class ProcessingStage(StrEnum):
    INSPECTING = "inspecting"
    PLANNING = "planning"
    PROCESSING = "processing"
    SCORING = "scoring"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    COMPLETED = "completed"


class QualityScore(BaseModel):
    extraction_accuracy: float = Field(ge=0, le=1)
    structural_fidelity: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    markdown_consistency: float = Field(ge=0, le=1)
    overall: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_overall_mean(self) -> QualityScore:
        expected = (
            self.extraction_accuracy
            + self.structural_fidelity
            + self.completeness
            + self.markdown_consistency
        ) / 4
        if abs(self.overall - expected) > 1e-6:
            raise ValueError("overall must equal the arithmetic mean of quality dimensions")
        return self


class RegionObservation(BaseModel):
    region_id: str
    region_type: RegionType
    bbox: BoundingBox
    content: str
    native_text: str
    native_healthy: bool
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)


class PageObservation(BaseModel):
    page_number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    native_healthy: bool
    regions: list[RegionObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_region_ids(self) -> PageObservation:
        region_ids = [region.region_id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region IDs must be unique within a page")
        return self


class DocumentContext(BaseModel):
    page_count: int = Field(ge=1)
    completed_pages: int = Field(default=0, ge=0)
    region_type_counts: dict[str, int] = Field(default_factory=dict)
    headings: list[str] = Field(default_factory=list)
    repeated_marginalia: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_progress_and_counts(self) -> DocumentContext:
        if self.completed_pages > self.page_count:
            raise ValueError("completed_pages cannot exceed page_count")
        if any(count < 0 for count in self.region_type_counts.values()):
            raise ValueError("region_type_counts values must be non-negative")
        return self


class RegionPlan(BaseModel):
    region_id: str
    strategy: ProcessingStrategy
    expert: ExpertKind
    difficulty: float = Field(ge=0, le=1)
    rationale: str
    risk_flags: list[str] = Field(default_factory=list)
    prompt_variant: str = "primary"


class PagePlan(BaseModel):
    page_number: int = Field(ge=1)
    source: Literal["model", "deterministic"]
    regions: list[RegionPlan] = Field(default_factory=list)
    rationale: str
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_region_ids(self) -> PagePlan:
        region_ids = [region.region_id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region IDs in a plan must be unique within a page")
        return self


class AttemptRecord(BaseModel):
    attempt: int = Field(ge=1)
    strategy: ProcessingStrategy
    expert: ExpertKind
    prompt_id: str = "unknown"
    prompt_version: str
    prompt_variant: str
    source: RegionSource = "fallback"
    model: str | None = None
    output: str
    score: QualityScore
    verdict: QualityStatus
    reason: str
    repair_hint: str | None = None
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = Field(ge=0)
    eval_count: int | None = Field(default=None, ge=0)
    prompt_eval_count: int | None = Field(default=None, ge=0)


class VisualVerification(BaseModel):
    region_id: str
    bbox: BoundingBox
    status: QualityStatus
    methods: list[VerificationMethod] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class RegionDecision(BaseModel):
    observation: RegionObservation
    plan: RegionPlan
    attempts: list[AttemptRecord] = Field(default_factory=list)
    selected_attempt_index: int = Field(ge=0)
    final_status: QualityStatus
    visual_verification: VisualVerification | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> RegionDecision:
        if self.observation.region_id != self.plan.region_id:
            raise ValueError("observation and plan region_id must match")
        if not self.attempts:
            raise ValueError("attempts must contain at least one attempt")
        if self.selected_attempt_index >= len(self.attempts):
            raise ValueError("selected_attempt_index must reference an attempt")
        attempt_numbers = [attempt.attempt for attempt in self.attempts]
        if len(attempt_numbers) != len(set(attempt_numbers)):
            raise ValueError("attempt numbers must be unique")
        if self.final_status != self.attempts[self.selected_attempt_index].verdict:
            raise ValueError("final_status must match the selected attempt verdict")
        return self


class PageDiagnostics(BaseModel):
    schema_version: Literal["1"] = "1"
    planning_mode: PlanningMode
    stage: ProcessingStage
    page_number: int = Field(ge=1)
    plan: PagePlan | None = None
    region_decisions: list[RegionDecision] = Field(default_factory=list)
    quality_score: QualityScore | None = None
    quality_status: QualityStatus
    repair_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str

    @model_validator(mode="after")
    def validate_plan_page(self) -> PageDiagnostics:
        if self.plan is not None and self.plan.page_number != self.page_number:
            raise ValueError("plan page_number must match diagnostics page_number")
        return self
