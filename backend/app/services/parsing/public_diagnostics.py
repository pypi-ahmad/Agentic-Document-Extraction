"""Allowlisted diagnostics contracts safe for API and artifact consumers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.services.parsing.agentic_contracts import (
    ExpertKind,
    PageDiagnostics,
    PlanningMode,
    ProcessingStage,
    ProcessingStrategy,
    QualityScore,
    QualityStatus,
    VerificationMethod,
)
from app.services.parsing.contracts import BoundingBox, RegionSource, RegionType


class PublicRegionObservation(BaseModel):
    region_id: str
    region_type: RegionType
    bbox: BoundingBox
    native_healthy: bool
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)


class PublicRegionPlan(BaseModel):
    region_id: str
    strategy: ProcessingStrategy
    expert: ExpertKind
    difficulty: float = Field(ge=0, le=1)
    risk_flags: list[str] = Field(default_factory=list)
    prompt_variant: str = "primary"


class PublicPagePlan(BaseModel):
    page_number: int = Field(ge=1)
    source: Literal["model", "deterministic"]
    regions: list[PublicRegionPlan] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_region_ids(self) -> PublicPagePlan:
        region_ids = [region.region_id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region IDs in a plan must be unique within a page")
        return self


class PublicAttemptRecord(BaseModel):
    attempt: int = Field(ge=1)
    strategy: ProcessingStrategy
    expert: ExpertKind
    prompt_id: str
    prompt_version: str
    prompt_variant: str
    source: RegionSource = "fallback"
    model: str | None = None
    score: QualityScore
    verdict: QualityStatus
    reason: str
    repair_hint: str | None = None
    warnings: list[str] = Field(default_factory=list)
    latency_ms: float = Field(ge=0)
    eval_count: int | None = Field(default=None, ge=0)
    prompt_eval_count: int | None = Field(default=None, ge=0)


class PublicVisualVerification(BaseModel):
    region_id: str
    bbox: BoundingBox
    status: QualityStatus
    methods: list[VerificationMethod] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class PublicRegionDecision(BaseModel):
    observation: PublicRegionObservation
    plan: PublicRegionPlan
    attempts: list[PublicAttemptRecord] = Field(default_factory=list)
    selected_attempt_index: int = Field(ge=0)
    final_status: QualityStatus
    visual_verification: PublicVisualVerification | None = None

    @model_validator(mode="after")
    def validate_decision(self) -> PublicRegionDecision:
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


class PublicPageDiagnostics(BaseModel):
    schema_version: Literal["1"] = "1"
    planning_mode: PlanningMode
    stage: ProcessingStage
    page_number: int = Field(ge=1)
    plan: PublicPagePlan | None = None
    region_decisions: list[PublicRegionDecision] = Field(default_factory=list)
    quality_score: QualityScore | None = None
    quality_status: QualityStatus
    repair_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    fingerprint: str

    @model_validator(mode="after")
    def validate_plan_page(self) -> PublicPageDiagnostics:
        if self.plan is not None and self.plan.page_number != self.page_number:
            raise ValueError("plan page_number must match diagnostics page_number")
        return self


def to_public_diagnostics(diagnostics: PageDiagnostics) -> PublicPageDiagnostics:
    """Copy only explicitly approved fields from an internal checkpoint."""
    plan = None
    if diagnostics.plan is not None:
        plan = PublicPagePlan(
            page_number=diagnostics.plan.page_number,
            source=diagnostics.plan.source,
            regions=[
                PublicRegionPlan(
                    region_id=region.region_id,
                    strategy=region.strategy,
                    expert=region.expert,
                    difficulty=region.difficulty,
                    risk_flags=list(region.risk_flags),
                    prompt_variant=region.prompt_variant,
                )
                for region in diagnostics.plan.regions
            ],
            warnings=list(diagnostics.plan.warnings),
        )

    decisions = []
    for decision in diagnostics.region_decisions:
        observation = decision.observation
        region_plan = decision.plan
        decisions.append(
            PublicRegionDecision(
                observation=PublicRegionObservation(
                    region_id=observation.region_id,
                    region_type=observation.region_type,
                    bbox=observation.bbox,
                    native_healthy=observation.native_healthy,
                    confidence=observation.confidence,
                    risk_flags=list(observation.risk_flags),
                ),
                plan=PublicRegionPlan(
                    region_id=region_plan.region_id,
                    strategy=region_plan.strategy,
                    expert=region_plan.expert,
                    difficulty=region_plan.difficulty,
                    risk_flags=list(region_plan.risk_flags),
                    prompt_variant=region_plan.prompt_variant,
                ),
                attempts=[
                    PublicAttemptRecord(
                        attempt=attempt.attempt,
                        strategy=attempt.strategy,
                        expert=attempt.expert,
                        prompt_id=attempt.prompt_id,
                        prompt_version=attempt.prompt_version,
                        prompt_variant=attempt.prompt_variant,
                        source=attempt.source,
                        model=attempt.model,
                        score=attempt.score,
                        verdict=attempt.verdict,
                        reason=attempt.reason,
                        repair_hint=attempt.repair_hint,
                        warnings=list(attempt.warnings),
                        latency_ms=attempt.latency_ms,
                        eval_count=attempt.eval_count,
                        prompt_eval_count=attempt.prompt_eval_count,
                    )
                    for attempt in decision.attempts
                ],
                selected_attempt_index=decision.selected_attempt_index,
                final_status=decision.final_status,
                visual_verification=(
                    PublicVisualVerification(
                        region_id=decision.visual_verification.region_id,
                        bbox=decision.visual_verification.bbox,
                        status=decision.visual_verification.status,
                        methods=list(decision.visual_verification.methods),
                        reasons=list(decision.visual_verification.reasons),
                    )
                    if decision.visual_verification
                    else None
                ),
            )
        )

    return PublicPageDiagnostics(
        schema_version=diagnostics.schema_version,
        planning_mode=diagnostics.planning_mode,
        stage=diagnostics.stage,
        page_number=diagnostics.page_number,
        plan=plan,
        region_decisions=decisions,
        quality_score=diagnostics.quality_score,
        quality_status=diagnostics.quality_status,
        repair_count=diagnostics.repair_count,
        warnings=list(diagnostics.warnings),
        fingerprint=diagnostics.fingerprint,
    )
