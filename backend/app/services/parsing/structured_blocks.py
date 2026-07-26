"""Canonical auditable document block graph and source-coordinate grounding."""

from __future__ import annotations

import hashlib
from io import BytesIO
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.services.parsing.contracts import BoundingBox, DocumentLayout, RegionType


class SourceBoundingBox(BaseModel):
    left: float = Field(ge=0)
    top: float = Field(ge=0)
    right: float = Field(gt=0)
    bottom: float = Field(gt=0)
    unit: Literal["pdf_points", "image_pixels", "normalized"]


class BlockProvenance(BaseModel):
    parser: str
    model: str | None = None
    prompt_version: str | None = None
    attempts: int = Field(default=1, ge=1)
    verification_status: str = "unverified"
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class TableCellBlock(BaseModel):
    id: str
    parent_id: str
    page: int
    source_page: int
    row: int
    column: int
    rowspan: int
    colspan: int
    text: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox


class ContentBlock(BaseModel):
    id: str
    page: int
    source_page: int
    order: int
    type: RegionType
    content: str
    content_sha256: str
    bbox: BoundingBox
    source_bbox: SourceBoundingBox
    page_width: float
    page_height: float
    parent_id: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    related_block_ids: list[str] = Field(default_factory=list)
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)
    provenance: BlockProvenance
    cells: list[TableCellBlock] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StructuredDocument(BaseModel):
    schema_version: Literal["paperplane-blocks/v1"] = "paperplane-blocks/v1"
    source_filename: str
    source_sha256: str
    page_count: int
    blocks: list[ContentBlock]
    warnings: list[str] = Field(default_factory=list)


def source_bbox(box: BoundingBox, width: float, height: float, unit: str) -> SourceBoundingBox:
    return SourceBoundingBox(
        left=box.left * width,
        top=box.top * height,
        right=box.right * width,
        bottom=box.bottom * height,
        unit=unit,
    )


def build_structured_document(
    document: DocumentLayout, *, source_filename: str, source_sha256: str
) -> StructuredDocument:
    stable = document.with_stable_ids()
    blocks: list[ContentBlock] = []
    heading_stack: list[tuple[int, str, str]] = []
    order = 0
    for page in stable.pages:
        for region in page.regions:
            order += 1
            region_id = region.id or f"p{page.page_number:04d}-r{order:04d}"
            level = region.heading_level or (1 if region.type == "title" else 2)
            if region.type in {"title", "heading"}:
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                parent_id = heading_stack[-1][1] if heading_stack else None
                heading_path = [item[2] for item in heading_stack] + [region.content.strip()]
                heading_stack.append((level, region_id, region.content.strip()))
            else:
                parent_id = region.parent_id or (heading_stack[-1][1] if heading_stack else None)
                heading_path = [item[2] for item in heading_stack]
            cells = [
                TableCellBlock(
                    id=cell.id or f"{region_id}-c{index:04d}",
                    parent_id=region_id,
                    page=page.page_number,
                    source_page=page.source_page_number or page.page_number,
                    row=cell.row,
                    column=cell.column,
                    rowspan=cell.rowspan,
                    colspan=cell.colspan,
                    text=cell.text,
                    bbox=cell.bbox,
                    source_bbox=source_bbox(
                        cell.bbox, page.width, page.height, page.coordinate_unit
                    ),
                )
                for index, cell in enumerate(region.table_cells, start=1)
            ]
            selected = next((item for item in region.recognition_candidates if item.selected), None)
            blocks.append(
                ContentBlock(
                    id=region_id,
                    page=page.page_number,
                    source_page=page.source_page_number or page.page_number,
                    order=order,
                    type=region.type,
                    content=region.content,
                    content_sha256=hashlib.sha256(region.content.encode()).hexdigest(),
                    bbox=region.bbox,
                    source_bbox=source_bbox(
                        region.bbox, page.width, page.height, page.coordinate_unit
                    ),
                    page_width=page.width,
                    page_height=page.height,
                    parent_id=parent_id,
                    heading_path=heading_path,
                    related_block_ids=list(region.related_region_ids),
                    confidence=region.confidence,
                    warnings=list(region.warnings),
                    provenance=BlockProvenance(
                        parser=region.source,
                        model=selected.model if selected else None,
                        attempts=max(1, len(region.recognition_candidates)),
                        verification_status=str(
                            region.semantic_metadata.get("verification_status", "unverified")
                        ),
                        candidates=[
                            item.model_dump(mode="json") for item in region.recognition_candidates
                        ],
                    ),
                    cells=cells,
                    metadata=dict(region.semantic_metadata),
                )
            )
    _link_continued_tables(blocks)
    return StructuredDocument(
        source_filename=source_filename,
        source_sha256=source_sha256,
        page_count=len(stable.pages),
        blocks=blocks,
        warnings=list(stable.warnings),
    )


def _link_continued_tables(blocks: list[ContentBlock]) -> None:
    tables = [block for block in blocks if block.type == "table" and block.cells]
    for previous, current in pairwise(tables):
        if current.page != previous.page + 1:
            continue
        previous_header = [cell.text.casefold().strip() for cell in previous.cells if cell.row == 0]
        current_header = [cell.text.casefold().strip() for cell in current.cells if cell.row == 0]
        if previous_header and previous_header == current_header:
            previous.related_block_ids.append(current.id)
            current.related_block_ids.append(previous.id)
            previous.metadata["continued_to"] = current.id
            current.metadata["continued_from"] = previous.id


def apply_source_geometry(
    document: DocumentLayout, source: bytes, source_filename: str
) -> DocumentLayout:
    """Attach original PDF-point or image-pixel geometry to parsed pages."""
    result = document.model_copy(deep=True)
    if Path(source_filename).suffix.lower() == ".pdf":
        import fitz

        pdf = fitz.open(stream=source, filetype="pdf")
        try:
            for page in result.pages:
                source_page = pdf[page.page_number - 1]
                page.width = float(source_page.rect.width)
                page.height = float(source_page.rect.height)
                page.coordinate_unit = "pdf_points"
        finally:
            pdf.close()
        return result

    from PIL import Image

    with Image.open(BytesIO(source)) as image:
        for page in result.pages:
            image.seek(page.page_number - 1)
            page.width = float(image.width)
            page.height = float(image.height)
            page.coordinate_unit = "image_pixels"
    return result
