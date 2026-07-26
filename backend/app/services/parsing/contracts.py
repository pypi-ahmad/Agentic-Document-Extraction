"""Normalized parser contracts independent of GLM-OCR's SDK payloads."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

RegionType = Literal[
    "title",
    "heading",
    "text",
    "list",
    "table",
    "chart",
    "formula",
    "figure",
    "header",
    "footer",
    "page_number",
    "code",
    "quote",
    "form_field",
    "checkbox",
    "signature",
    "seal",
]
RegionSource = Literal[
    "native",
    "paddleocr_vl",
    "paddle",
    "docling",
    "glm_ocr",
    "cloud_vlm",
    "fallback",
]


class RecognitionCandidate(BaseModel):
    source: RegionSource
    content: str
    model: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    latency_ms: float = Field(default=0, ge=0)
    selected: bool = False


class BoundingBox(BaseModel):
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_edges(self) -> BoundingBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("bounding box right/bottom must exceed left/top")
        return self


class TableCell(BaseModel):
    id: str | None = None
    page: int | None = Field(default=None, ge=1)
    parent_region_id: str | None = None
    bbox: BoundingBox
    text: str = ""
    row: int = Field(ge=0)
    column: int = Field(ge=0)
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)


class Region(BaseModel):
    id: str | None = None
    type: RegionType
    bbox: BoundingBox
    content: str
    source: RegionSource = "glm_ocr"
    source_label: str | None = None
    heading_level: int | None = Field(default=None, ge=1, le=6)
    order: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    crop_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    table_rows: list[list[str]] | None = None
    table_html: str | None = None
    table_cells: list[TableCell] = Field(default_factory=list)
    recognition_candidates: list[RecognitionCandidate] = Field(default_factory=list)
    column_index: int | None = Field(default=None, ge=0)
    is_spanning: bool = False
    parent_id: str | None = None
    related_region_ids: list[str] = Field(default_factory=list)
    semantic_metadata: dict[str, Any] = Field(default_factory=dict)


class NativeWord(BaseModel):
    text: str
    bbox: BoundingBox


class PageLayout(BaseModel):
    page_number: int = Field(ge=1)
    source_page_number: int | None = Field(default=None, ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    coordinate_unit: Literal["pdf_points", "image_pixels", "normalized"] = "normalized"
    regions: list[Region] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    routing: str | None = None


class DocumentLayout(BaseModel):
    pages: list[PageLayout] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def with_stable_ids(self) -> DocumentLayout:
        clone = self.model_copy(deep=True)
        for page in clone.pages:
            for index, region in enumerate(page.regions, start=1):
                region.id = f"p{page.page_number:04d}-r{index:04d}"
                for cell_index, cell in enumerate(region.table_cells, start=1):
                    cell.id = f"{region.id}-c{cell_index:04d}"
                    cell.page = page.page_number
                    cell.parent_region_id = region.id
        return clone


class ContextChunk(BaseModel):
    id: str
    ordinal: int = Field(ge=1)
    page: int = Field(ge=1)
    source_page: int | None = Field(default=None, ge=1)
    bbox: BoundingBox
    source_bbox: dict[str, Any] | None = None
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)
    type: RegionType
    source: RegionSource
    confidence: float | None = Field(default=None, ge=0, le=1)
    heading_path: list[str] = Field(default_factory=list)
    parent_id: str | None = None
    column_index: int | None = Field(default=None, ge=0)
    is_spanning: bool = False
    related_region_ids: list[str] = Field(default_factory=list)
    markdown: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class StitchResult(BaseModel):
    clean_markdown: str
    grounded_markdown: str
    context_chunks: list[ContextChunk]
