"""Canonical grounded contracts for the OpenAI-only V2 pipeline."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.services.parsing.contracts import BoundingBox

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
    luna_reasoning_effort: Literal["none", "low", "medium"]
    terra_reasoning_effort: Literal["medium", "high"] | None
    terra_scope: Literal["none", "flagged", "complex"]
    max_repair_rounds: int


_MODE_POLICIES = {
    ProcessingMode.ECONOMY: ModePolicy(
        base_dpi=150,
        crop_dpi=300,
        luna_reasoning_effort="none",
        terra_reasoning_effort=None,
        terra_scope="none",
        max_repair_rounds=1,
    ),
    ProcessingMode.BALANCED: ModePolicy(
        base_dpi=200,
        crop_dpi=300,
        luna_reasoning_effort="low",
        terra_reasoning_effort="medium",
        terra_scope="flagged",
        max_repair_rounds=2,
    ),
    ProcessingMode.AUDIT: ModePolicy(
        base_dpi=250,
        crop_dpi=400,
        luna_reasoning_effort="medium",
        terra_reasoning_effort="high",
        terra_scope="complex",
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

    @model_validator(mode="after")
    def require_evidence_for_verified_content(self) -> GroundedChunk:
        if self.verification_status == VerificationStatus.VERIFIED and not self.grounding:
            raise ValueError("verified chunk requires grounding evidence")
        return self


class ExtractionField(BaseModel):
    value: Any | None = None
    status: Literal["grounded", "unresolved"]
    citations: list[str] = Field(default_factory=list)
    reason: str | None = None

    @model_validator(mode="after")
    def enforce_supported_values(self) -> ExtractionField:
        if self.status == "grounded" and not self.citations:
            raise ValueError("grounded field requires at least one citation")
        if self.status == "unresolved" and self.value is not None:
            raise ValueError("unresolved field value must be null")
        return self


class DocumentSplit(BaseModel):
    id: str
    classification: str
    identifier: str | None = None
    pages: list[int] = Field(min_length=1)
    chunk_ids: list[str] = Field(default_factory=list)
    boundary_reasons: list[str] = Field(default_factory=list)


class DocumentResult(BaseModel):
    schema_version: Literal["paperplane-document/v2"] = "paperplane-document/v2"
    source_filename: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)
    markdown: str
    chunks: list[GroundedChunk]
    splits: list[DocumentSplit] = Field(default_factory=list)
    extraction: dict[str, ExtractionField] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_grounded_graph(self) -> DocumentResult:
        chunk_ids = [chunk.id for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk IDs must be unique")
        known_ids = set(chunk_ids)
        for chunk in self.chunks:
            if chunk.page > self.page_count:
                raise ValueError(f"chunk {chunk.id} references page outside document")
            anchor = f'<a id="{chunk.id}"></a>'
            if anchor not in self.markdown:
                raise ValueError(f"missing Markdown anchor for chunk {chunk.id}")
            related_ids = set(chunk.children)
            if chunk.parent_id:
                related_ids.add(chunk.parent_id)
            unknown = related_ids - known_ids
            if unknown:
                raise ValueError(f"chunk {chunk.id} references unknown chunk {sorted(unknown)[0]}")
        for name, field in self.extraction.items():
            for citation in field.citations:
                if citation not in known_ids:
                    raise ValueError(f"field {name} has unknown citation {citation}")
        for split in self.splits:
            if any(page < 1 or page > self.page_count for page in split.pages):
                raise ValueError(f"split {split.id} references page outside document")
            unknown = set(split.chunk_ids) - known_ids
            if unknown:
                raise ValueError(f"split {split.id} references unknown chunk {sorted(unknown)[0]}")
        return self


__all__ = [
    "BoundingBox",
    "DocumentResult",
    "DocumentSplit",
    "ExtractionField",
    "GroundedChunk",
    "Grounding",
    "GroundingMethod",
    "ModePolicy",
    "ProcessingMode",
    "VerificationStatus",
    "mode_policy",
]
