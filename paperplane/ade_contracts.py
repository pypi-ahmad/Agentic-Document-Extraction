"""Versioned ADE-style public contracts and Paperplane engine selection."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from paperplane.contracts import ModelTokenUsage, ParseResponse, StructureNode
from paperplane.document_intelligence import infer_document_relations

EngineKind = Literal["docling", "pdf_inspector", "cloud_ai", "ollama"]


class EngineOptions(BaseModel):
    """UI-neutral engine switches. An empty selection is valid until Parse is pressed."""

    docling: bool = False
    pdf_inspector: bool = False
    cloud_ai: bool = False
    ollama: bool = False
    cloud_enhancement: bool = False

    @model_validator(mode="after")
    def validate_selection(self) -> EngineOptions:
        if len(self.enabled_engines) > 1:
            raise ValueError("Select exactly one processing engine")
        if self.cloud_ai and self.cloud_enhancement:
            raise ValueError("Cloud AI is already an AI engine and cannot enable enhancement")
        return self

    @property
    def enabled_engines(self) -> list[EngineKind]:
        return [
            name
            for name in ("docling", "pdf_inspector", "cloud_ai", "ollama")
            if getattr(self, name)
        ]

    @property
    def selected_engine(self) -> EngineKind | None:
        return self.enabled_engines[0] if self.enabled_engines else None

    @property
    def uses_cloud(self) -> bool:
        return self.cloud_ai or self.cloud_enhancement

    def require_selected(self) -> EngineKind:
        if self.selected_engine is None:
            raise ValueError("Select exactly one processing engine")
        return self.selected_engine


class ADEBox(BaseModel):
    xmin: float = Field(ge=0, le=1)
    ymin: float = Field(ge=0, le=1)
    xmax: float = Field(ge=0, le=1)
    ymax: float = Field(ge=0, le=1)


class ADERange(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class ADEGrounding(BaseModel):
    page: int = Field(ge=1)
    range: ADERange
    box: ADEBox


class ADEStructureNode(BaseModel):
    id: str
    type: str
    grounding: ADEGrounding | None = None
    atomic_grounding: list[ADEGrounding] | None = None
    status: Literal["ok", "failed"] | None = None
    reason: str | None = None
    row: int | None = None
    col: int | None = None
    rowspan: int | None = None
    colspan: int | None = None
    children: list[ADEStructureNode] = Field(default_factory=list)


class ADEBilling(BaseModel):
    service_tier: str
    total_credits: float = Field(ge=0)


class ADEParseMetadata(BaseModel):
    job_id: str
    model_version: str
    page_count: int = Field(ge=1)
    output_markdown_chars: int = Field(ge=0)
    range_units: Literal["unicode_codepoints"] = "unicode_codepoints"
    openapi_spec: str = "paperplane://contracts/ade-v2-parse/5.0.0"
    failed_pages: list[int] = Field(default_factory=list)
    duration_ms: int | None = None
    billing: ADEBilling


class ADEParseResponse(BaseModel):
    """Paperplane's strict, serializable ADE v2 Parse compatibility export."""

    markdown: str
    metadata: ADEParseMetadata
    structure: ADEStructureNode


class WordGrounding(BaseModel):
    """Paperplane extension; emitted only for observed/aligned words."""

    text: str
    grounding: ADEGrounding
    confidence: float | None = Field(default=None, ge=0, le=1)
    confidence_kind: Literal["calibrated", "raw_uncalibrated"] = "raw_uncalibrated"


class PaperplaneParseExport(BaseModel):
    contract: Literal["paperplane.parse.v5"] = "paperplane.parse.v5"
    ade: ADEParseResponse
    engine: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    words: list[WordGrounding] = Field(default_factory=list)
    relations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_usage: dict[str, ModelTokenUsage] = Field(default_factory=dict)


def _box(node: StructureNode) -> ADEBox:
    if node.box is None:
        return ADEBox(xmin=0, ymin=0, xmax=1, ymax=1)
    return ADEBox(
        xmin=node.box.left,
        ymin=node.box.top,
        xmax=node.box.right,
        ymax=node.box.bottom,
    )


def _range(node: StructureNode) -> ADERange:
    if not node.ranges:
        return ADERange(start=0, end=0)
    return ADERange(start=node.ranges[0].start, end=node.ranges[-1].end)


def to_ade_v2_parse(
    response: ParseResponse,
    *,
    model_version: str = "paperplane-5.0.0",
) -> ADEParseResponse:
    """Convert the internal grounded response to the documented ADE v2 shape."""

    counters: defaultdict[str, int] = defaultdict(int)

    def node_id(node_type: str) -> str:
        index = counters[node_type]
        counters[node_type] += 1
        return f"{node_type}-{index}"

    def content_node(node: StructureNode, physical_page: int) -> ADEStructureNode:
        grounding = ADEGrounding(page=physical_page, range=_range(node), box=_box(node))
        atomic = [
            ADEGrounding(
                page=physical_page,
                range=ADERange(start=line.ranges[0].start, end=line.ranges[-1].end),
                box=ADEBox(
                    xmin=line.box.left,
                    ymin=line.box.top,
                    xmax=line.box.right,
                    ymax=line.box.bottom,
                ),
            )
            for line in node.atomic_grounding
        ]
        if node.type == "table":
            atomic = []
        return ADEStructureNode(
            id=node_id(node.type),
            type=node.type,
            grounding=grounding,
            atomic_grounding=(atomic if node.type == "table_cell" else atomic or None),
            row=node.row,
            col=node.col,
            rowspan=node.rowspan,
            colspan=node.colspan,
            children=[content_node(child, physical_page) for child in node.children],
        )

    pages: list[ADEStructureNode] = []
    for page in response.structure.children:
        physical_page = page.page or len(pages) + 1
        children = [content_node(child, physical_page) for child in page.children]
        start = min(
            (child.grounding.range.start for child in children if child.grounding), default=0
        )
        end = max(
            (child.grounding.range.end for child in children if child.grounding), default=start
        )
        failed = physical_page in response.metadata.failed_pages
        pages.append(
            ADEStructureNode(
                id=node_id("page"),
                type="page",
                grounding=ADEGrounding(
                    page=physical_page,
                    range=ADERange(start=start, end=end),
                    box=ADEBox(xmin=0, ymin=0, xmax=1, ymax=1),
                ),
                status="failed" if failed else "ok",
                reason="Page processing failed" if failed else None,
                children=children,
            )
        )

    page_count = response.metadata.source_page_count or response.metadata.page_count
    return ADEParseResponse(
        markdown=response.markdown,
        metadata=ADEParseMetadata(
            job_id=response.metadata.job_id,
            model_version=model_version,
            page_count=page_count,
            output_markdown_chars=len(response.markdown),
            failed_pages=response.metadata.failed_pages,
            duration_ms=response.metadata.duration_ms,
            billing=ADEBilling(
                service_tier=response.metadata.service_tier or "local",
                total_credits=response.metadata.total_credits,
            ),
        ),
        structure=ADEStructureNode(id="document-0", type="document", children=pages),
    )


def to_paperplane_export(
    response: ParseResponse,
    *,
    words: list[WordGrounding] | None = None,
    relations: list[dict[str, Any]] | None = None,
    provenance: dict[str, Any] | None = None,
) -> PaperplaneParseExport:
    exported_words = words
    if exported_words is None:
        exported_words = [
            WordGrounding(
                text=word.text,
                grounding=ADEGrounding(
                    page=word.page,
                    range=ADERange(start=word.range.start, end=word.range.end),
                    box=ADEBox(
                        xmin=word.box.left,
                        ymin=word.box.top,
                        xmax=word.box.right,
                        ymax=word.box.bottom,
                    ),
                ),
                confidence=word.raw_confidence,
            )
            for word in response.words
        ]
    return PaperplaneParseExport(
        ade=to_ade_v2_parse(response),
        engine=response.metadata.engine,
        provenance=provenance or {},
        words=exported_words,
        relations=relations if relations is not None else infer_document_relations(response),
        warnings=response.metadata.warnings,
        model_usage=response.metadata.model_usage,
    )


__all__ = [
    "ADEParseResponse",
    "EngineKind",
    "EngineOptions",
    "PaperplaneParseExport",
    "WordGrounding",
    "to_ade_v2_parse",
    "to_paperplane_export",
]
