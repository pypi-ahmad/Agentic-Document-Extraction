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


class MarkdownSpan(BaseModel):
    """Half-open Unicode code-point offsets into a page's Markdown."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def require_ordered_offsets(self) -> MarkdownSpan:
        if self.end < self.start:
            raise ValueError("markdown span end must be greater than or equal to start")
        return self


class ItemVerification(BaseModel):
    status: VerificationStatus = VerificationStatus.CANDIDATE
    model: str
    pass_name: str = Field(alias="pass")
    warnings: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class DocumentItem(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    order: int = Field(ge=1)
    type: ChunkType
    text: str
    markdown_span: MarkdownSpan
    parent_id: str | None = None
    grounding: list[Grounding] = Field(default_factory=list)
    verification: ItemVerification

    @model_validator(mode="after")
    def require_verified_evidence(self) -> DocumentItem:
        if self.verification.status == VerificationStatus.VERIFIED and not self.grounding:
            raise ValueError("verified item requires grounding evidence")
        return self


class PageDimensions(BaseModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: Literal["pdf_points", "image_pixels"]


class DocumentPage(BaseModel):
    number: int = Field(ge=1)
    dimensions: PageDimensions
    verification_status: VerificationStatus
    markdown: str
    warnings: list[str] = Field(default_factory=list)
    items: list[DocumentItem] = Field(default_factory=list)


class SourceDocument(BaseModel):
    filename: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = "application/pdf"
    page_count: int = Field(ge=1)


class QualitySummary(BaseModel):
    verified_items: int = Field(default=0, ge=0)
    candidate_items: int = Field(default=0, ge=0)
    unresolved_items: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)


class SchemaExtraction(BaseModel):
    data: Any
    fields: dict[str, ExtractionField] = Field(default_factory=dict)


class DocumentSplit(BaseModel):
    id: str
    classification: str
    identifier: str | None = None
    pages: list[int] = Field(min_length=1)
    item_ids: list[str] = Field(default_factory=list)
    boundary_reasons: list[str] = Field(default_factory=list)


class DocumentResult(BaseModel):
    schema_version: Literal["paperplane-document/v3"] = "paperplane-document/v3"
    source: SourceDocument
    status: Literal["completed", "completed_with_warnings"]
    quality_summary: QualitySummary = Field(default_factory=QualitySummary)
    pages: list[DocumentPage] = Field(min_length=1)
    splits: list[DocumentSplit] = Field(default_factory=list)
    extraction: SchemaExtraction | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    processing: dict[str, Any]

    @model_validator(mode="after")
    def validate_grounded_graph(self) -> DocumentResult:
        partial = bool(self.processing.get("partial"))
        if not partial and len(self.pages) != self.source.page_count:
            raise ValueError("page count does not match source")
        page_numbers = [page.number for page in self.pages]
        if not partial and page_numbers != list(range(1, self.source.page_count + 1)):
            raise ValueError("pages must be contiguous and ordered")
        if partial and (
            page_numbers != sorted(set(page_numbers))
            or any(page > self.source.page_count for page in page_numbers)
        ):
            raise ValueError("partial pages must be unique, ordered, and within the source")
        items = [item for page in self.pages for item in page.items]
        item_ids = [item.id for item in items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("item IDs must be unique")
        known_ids = set(item_ids)
        page_by_item = {item.id: page.number for page in self.pages for item in page.items}
        for page in self.pages:
            for item in page.items:
                if item.markdown_span.end > len(page.markdown):
                    raise ValueError(f"item {item.id} markdown span is outside page markdown")
                if item.parent_id:
                    if item.parent_id not in known_ids:
                        raise ValueError(f"item {item.id} references unknown item {item.parent_id}")
                    if page_by_item[item.parent_id] != page.number:
                        raise ValueError(f"item {item.id} parent must be on the same page")
        for name, field in (self.extraction.fields if self.extraction else {}).items():
            for citation in field.citations:
                if citation not in known_ids:
                    raise ValueError(f"field {name} has unknown citation {citation}")
        for split in self.splits:
            if any(page < 1 or page > self.source.page_count for page in split.pages):
                raise ValueError(f"split {split.id} references page outside document")
            unknown = set(split.item_ids) - known_ids
            if unknown:
                raise ValueError(f"split {split.id} references unknown chunk {sorted(unknown)[0]}")
        return self


__all__ = [
    "BoundingBox",
    "DocumentItem",
    "DocumentPage",
    "DocumentResult",
    "DocumentSplit",
    "ExtractionField",
    "GroundedChunk",
    "Grounding",
    "GroundingMethod",
    "ItemVerification",
    "MarkdownSpan",
    "ModePolicy",
    "PageDimensions",
    "ProcessingMode",
    "QualitySummary",
    "SchemaExtraction",
    "SourceDocument",
    "VerificationStatus",
    "mode_policy",
]
