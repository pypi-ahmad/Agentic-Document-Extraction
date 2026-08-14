"""Grounded contracts used by the OpenAI page pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from paperplane.types import BoundingBox

ChunkType = Literal[
    "title",
    "heading",
    "text",
    "list",
    "checkbox",
    "table",
    "table_cell",
    "form_field",
    "figure",
    "chart",
    "header",
    "footer",
]


class ProcessingMode(StrEnum):
    ECONOMY = "economy"
    BALANCED = "balanced"
    AUDIT = "audit"


class GroundingMethod(StrEnum):
    TEXT_LAYER_EXACT = "text_layer_exact"
    VISION_REFINED = "vision_refined"


class VerificationStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    UNRESOLVED = "unresolved"


class ModePolicy(BaseModel):
    base_dpi: int
    crop_dpi: int
    draft_reasoning_effort: Literal["none", "low", "medium"]
    verification_reasoning_effort: Literal["medium", "high"] | None
    verification_scope: Literal["none", "flagged", "complex"]
    max_repair_rounds: int


_MODE_POLICIES = {
    ProcessingMode.ECONOMY: ModePolicy(
        base_dpi=150,
        crop_dpi=300,
        draft_reasoning_effort="none",
        verification_reasoning_effort=None,
        verification_scope="none",
        max_repair_rounds=1,
    ),
    ProcessingMode.BALANCED: ModePolicy(
        base_dpi=200,
        crop_dpi=300,
        draft_reasoning_effort="low",
        verification_reasoning_effort="medium",
        verification_scope="flagged",
        max_repair_rounds=2,
    ),
    ProcessingMode.AUDIT: ModePolicy(
        base_dpi=250,
        crop_dpi=400,
        draft_reasoning_effort="medium",
        verification_reasoning_effort="high",
        verification_scope="complex",
        max_repair_rounds=3,
    ),
}


def mode_policy(mode: ProcessingMode) -> ModePolicy:
    return _MODE_POLICIES[mode].model_copy(deep=True)


class Grounding(BaseModel):
    page: int = Field(ge=1)
    box: BoundingBox
    method: GroundingMethod
    source_box: tuple[float, float, float, float]
    source_unit: Literal["pdf_points", "image_pixels"]
    evidence_artifact_id: str = Field(min_length=1)


class AtomicLine(BaseModel):
    text: str = Field(min_length=1)
    box: BoundingBox


class GroundedChunk(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    page: int = Field(ge=1)
    order: int = Field(ge=1)
    type: ChunkType
    text: str
    markdown: str
    grounding: list[Grounding] = Field(default_factory=list)
    parent_id: str | None = None
    children: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.CANDIDATE
    source_model: str
    source_pass: str
    warnings: list[str] = Field(default_factory=list)
    atomic_lines: list[AtomicLine] = Field(default_factory=list)
    row: int | None = Field(default=None, ge=0)
    col: int | None = Field(default=None, ge=0)
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def require_evidence_for_verified_content(self) -> GroundedChunk:
        if self.verification_status == VerificationStatus.VERIFIED and not self.grounding:
            raise ValueError("verified chunk requires grounding evidence")
        return self


__all__ = [
    "AtomicLine",
    "BoundingBox",
    "GroundedChunk",
    "Grounding",
    "GroundingMethod",
    "ModePolicy",
    "ProcessingMode",
    "VerificationStatus",
    "mode_policy",
]
