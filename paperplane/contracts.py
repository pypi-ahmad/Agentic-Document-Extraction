"""Grounded Parse contracts and deterministic response assembly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

BlockType = Literal[
    "text",
    "table",
    "table_cell",
    "figure",
    "marginalia",
    "attestation",
    "logo",
    "card",
    "scan_code",
]
StructureType = Literal[
    "document",
    "page",
    "text",
    "table",
    "table_cell",
    "figure",
    "marginalia",
    "attestation",
    "logo",
    "card",
    "scan_code",
]
GroundingStatus = Literal["grounded", "semantic_only"]
ParserEngine = Literal[
    "docling",
    "openai_vision",
    "xai_vision",
    "google_vision",
    "anthropic_vision",
    "agnes_vision",
]


class NormalizedBox(BaseModel):
    """A document-relative bounding box with coordinates in the [0, 1] interval."""

    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def require_non_empty_area(self) -> NormalizedBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("normalized box right/bottom must exceed left/top")
        return self


class CodepointRange(BaseModel):
    """Half-open Unicode code-point offsets into document Markdown."""

    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def require_ordered_offsets(self) -> CodepointRange:
        if self.end < self.start:
            raise ValueError("range end must be greater than or equal to start")
        return self


class AtomicGrounding(BaseModel):
    """One visual line grounded against a parent block's Markdown range."""

    text: str
    box: NormalizedBox
    ranges: list[CodepointRange] = Field(min_length=1)


class StructureNode(BaseModel):
    """Document hierarchy node, ordered as document → page → block → table cell."""

    id: str = Field(min_length=1)
    type: StructureType
    page: int | None = Field(default=None, ge=1)
    parser: ParserEngine | None = None
    grounding_status: GroundingStatus = "grounded"
    box: NormalizedBox | None = None
    ranges: list[CodepointRange] = Field(default_factory=list)
    text: str | None = None
    semantic_role: str | None = None
    row: int | None = Field(default=None, ge=0)
    col: int | None = Field(default=None, ge=0)
    rowspan: int | None = Field(default=None, ge=1)
    colspan: int | None = Field(default=None, ge=1)
    atomic_grounding: list[AtomicGrounding] = Field(default_factory=list)
    children: list[StructureNode] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_node_shape(self) -> StructureNode:
        if self.type in {"document", "page"}:
            if self.box is not None or self.ranges:
                raise ValueError("document and page nodes cannot have grounding geometry or ranges")
        elif not self.ranges:
            raise ValueError("block nodes require at least one Markdown range")
        elif self.grounding_status == "grounded" and (self.box is None or self.page is None):
            raise ValueError("grounded blocks require a page and normalized box")
        elif self.grounding_status == "semantic_only" and self.box is not None:
            raise ValueError("semantic-only blocks cannot claim a normalized box")

        if self.type == "table_cell":
            if self.row is None or self.col is None:
                raise ValueError("table cells require row and col")
            if self.children:
                raise ValueError("table cells cannot have children")
        elif any(value is not None for value in (self.row, self.col, self.rowspan, self.colspan)):
            raise ValueError("table coordinates are only valid on table cells")
        return self


class ParseMetadata(BaseModel):
    job_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    ai_model: str | None = None
    page_count: int = Field(ge=1)
    output_characters: int = Field(ge=0)
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_tokens: int = Field(default=0, ge=0)
    range_units: Literal["unicode_codepoints"] = "unicode_codepoints"
    failed_pages: list[int] = Field(default_factory=list)
    duration_ms: int | None = Field(default=None, ge=0)
    service_tier: str | None = None
    total_credits: int = Field(default=0, ge=0)
    source_format: str = Field(default="unknown", min_length=1)
    engine: Literal[
        "docling",
        "openai_vision",
        "xai_vision",
        "google_vision",
        "anthropic_vision",
        "agnes_vision",
        "hybrid",
    ] = "openai_vision"
    warnings: list[str] = Field(default_factory=list)


class ParseResponse(BaseModel):
    markdown: str
    metadata: ParseMetadata
    structure: StructureNode

    @model_validator(mode="after")
    def validate_grounded_document(self) -> ParseResponse:
        if self.metadata.output_characters != len(self.markdown):
            raise ValueError("output_characters must match Markdown Unicode code-point length")
        if self.structure.type != "document" or self.structure.id != "document-1":
            raise ValueError("structure root must be document-1")
        pages = self.structure.children
        if len(pages) != self.metadata.page_count:
            raise ValueError("page_count must match structure pages")

        expected_ids: dict[str, int] = {}
        for page_index, page in enumerate(pages, start=1):
            if page.type != "page" or page.id != f"page-{page_index}":
                raise ValueError("pages must be contiguous and ordered")
            for block in page.children:
                self._validate_block(block, page.page, expected_ids, parent_type=None)
        return self

    def _validate_block(
        self,
        node: StructureNode,
        page_number: int | None,
        expected_ids: dict[str, int],
        parent_type: str | None,
    ) -> None:
        if node.type in {"document", "page"}:
            raise ValueError("page children must be content blocks")
        if node.page != page_number:
            raise ValueError("blocks must belong to their containing page")
        if node.type == "table_cell" and parent_type != "table":
            raise ValueError("table cells must be children of tables")
        if node.type != "table_cell" and parent_type is not None:
            raise ValueError("only table cells may be nested beneath a block")

        expected_ids[node.type] = expected_ids.get(node.type, 0) + 1
        if node.id != f"{node.type}-{expected_ids[node.type]}":
            raise ValueError("public IDs must be stable <type>-<index> values")
        self._validate_ranges(node.ranges, parent_ranges=None)
        previous_atomic_end = -1
        for grounding in node.atomic_grounding:
            self._validate_ranges(grounding.ranges, parent_ranges=node.ranges)
            for item in grounding.ranges:
                if item.start < previous_atomic_end:
                    raise ValueError("atomic grounding ranges must be ordered and non-overlapping")
                previous_atomic_end = item.end
            text = "".join(self.markdown[item.start : item.end] for item in grounding.ranges)
            if text != grounding.text:
                raise ValueError("atomic grounding text must match its Markdown ranges")
        for child in node.children:
            self._validate_block(child, page_number, expected_ids, parent_type=node.type)

    def _validate_ranges(
        self,
        ranges: list[CodepointRange],
        parent_ranges: list[CodepointRange] | None,
    ) -> None:
        previous_end = -1
        for item in ranges:
            if item.end > len(self.markdown):
                raise ValueError("range is outside document Markdown")
            if item.start < previous_end:
                raise ValueError("grounding ranges must be ordered and non-overlapping")
            if parent_ranges is not None and not any(
                parent.start <= item.start and item.end <= parent.end for parent in parent_ranges
            ):
                raise ValueError("atomic grounding must be contained by its parent block")
            previous_end = item.end


class AtomicLineInput(BaseModel):
    text: str = Field(min_length=1)
    box: NormalizedBox


class AgenticBlockInput(BaseModel):
    """Deterministic assembler input from a page agent; it is not an API contract."""

    type: BlockType
    markdown: str
    box: NormalizedBox | None = None
    grounding_status: GroundingStatus = "grounded"
    semantic_role: str | None = None
    atomic_lines: list[AtomicLineInput] = Field(default_factory=list)
    table_cells: list[AgenticBlockInput] = Field(default_factory=list)
    row: int | None = Field(default=None, ge=0)
    col: int | None = Field(default=None, ge=0)
    rowspan: int = Field(default=1, ge=1)
    colspan: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_input_shape(self) -> AgenticBlockInput:
        if self.grounding_status == "grounded" and self.box is None:
            raise ValueError("grounded block input requires a normalized box")
        if self.grounding_status == "semantic_only" and self.box is not None:
            raise ValueError("semantic-only block input cannot claim a normalized box")
        if self.type == "table_cell":
            if self.row is None or self.col is None:
                raise ValueError("table cell input requires row and col")
            if self.table_cells:
                raise ValueError("table cell input cannot contain table cells")
        elif self.row is not None or self.col is not None:
            raise ValueError("only table cell input accepts row and col")
        if self.type != "table" and self.table_cells:
            raise ValueError("only table input can contain table cells")
        if any(cell.type != "table_cell" for cell in self.table_cells):
            raise ValueError("table input children must be table cells")
        return self


class AgenticPageInput(BaseModel):
    page_number: int | None = Field(default=None, ge=1)
    parser: ParserEngine = "openai_vision"
    blocks: list[AgenticBlockInput] = Field(default_factory=list)


def _find_sequential(haystack: str, needle: str, cursor: int, *, error: str) -> tuple[int, int]:
    start = haystack.find(needle, cursor)
    if start < 0:
        raise ValueError(error)
    return start, start + len(needle)


def _find_table_cell(haystack: str, needle: str, cursor: int) -> tuple[int, int]:
    """Locate visible cell text without accidentally grounding it inside an HTML tag."""

    wrapped = f">{needle}<"
    wrapped_start = haystack.find(wrapped, cursor)
    if wrapped_start >= 0:
        start = wrapped_start + 1
        return start, start + len(needle)
    return _find_sequential(
        haystack,
        needle,
        cursor,
        error="table cell Markdown must occur in its parent table Markdown",
    )


def assemble_parse_response(
    *,
    document_id: str,
    job_id: str,
    model: str,
    pages: list[AgenticPageInput],
    ai_model: str | None = None,
    failed_pages: list[int] | None = None,
    duration_ms: int | None = None,
    source_format: str = "unknown",
    engine: Literal[
        "docling",
        "openai_vision",
        "xai_vision",
        "google_vision",
        "anthropic_vision",
        "agnes_vision",
        "hybrid",
    ] = "openai_vision",
    warnings: list[str] | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> ParseResponse:
    """Assemble page-agent observations into globally grounded Markdown without model calls."""

    physical_pages = [page.page_number for page in pages if page.page_number is not None]
    if physical_pages and physical_pages != sorted(physical_pages):
        raise ValueError("physical input pages must be ordered")

    parts: list[str] = []
    output_length = 0
    ids: dict[str, int] = {}
    page_nodes: list[StructureNode] = []

    def append(value: str) -> None:
        nonlocal output_length
        parts.append(value)
        output_length += len(value)

    def next_id(block_type: BlockType) -> str:
        ids[block_type] = ids.get(block_type, 0) + 1
        return f"{block_type}-{ids[block_type]}"

    for page_index, page in enumerate(pages):
        if page_index:
            append("\n\n<!-- PAGE BREAK -->\n\n")
        page_children: list[StructureNode] = []
        for block_index, block in enumerate(page.blocks):
            if block_index:
                append("\n\n")
            block_start = output_length
            append(block.markdown)
            block_ranges = [CodepointRange(start=block_start, end=output_length)]
            block_node = StructureNode(
                id=next_id(block.type),
                type=block.type,
                page=page.page_number,
                grounding_status=block.grounding_status,
                box=block.box,
                ranges=block_ranges,
                text=block.markdown,
                semantic_role=block.semantic_role,
                row=block.row if block.type == "table_cell" else None,
                col=block.col if block.type == "table_cell" else None,
                rowspan=block.rowspan if block.type == "table_cell" else None,
                colspan=block.colspan if block.type == "table_cell" else None,
                atomic_grounding=_assemble_atomic_grounding(
                    block.atomic_lines, block.markdown, block_start
                ),
            )
            if block.table_cells:
                cell_search_start = 0
                cells: list[StructureNode] = []
                for cell in block.table_cells:
                    local_start, local_end = _find_table_cell(
                        block.markdown, cell.markdown, cell_search_start
                    )
                    cell_search_start = local_end
                    cells.append(
                        StructureNode(
                            id=next_id("table_cell"),
                            type="table_cell",
                            page=page.page_number,
                            grounding_status=cell.grounding_status,
                            box=cell.box,
                            ranges=[
                                CodepointRange(
                                    start=block_start + local_start,
                                    end=block_start + local_end,
                                )
                            ],
                            text=cell.markdown,
                            semantic_role=cell.semantic_role,
                            row=cell.row,
                            col=cell.col,
                            rowspan=cell.rowspan,
                            colspan=cell.colspan,
                            atomic_grounding=_assemble_atomic_grounding(
                                cell.atomic_lines, cell.markdown, block_start + local_start
                            ),
                        )
                    )
                block_node.children = cells
            page_children.append(block_node)
        page_nodes.append(
            StructureNode(
                id=f"page-{page_index + 1}",
                type="page",
                page=page.page_number,
                parser=page.parser,
                children=page_children,
            )
        )

    append(f"\n\n<!-- doc_id={document_id} -->")
    markdown = "".join(parts)
    return ParseResponse(
        markdown=markdown,
        metadata=ParseMetadata(
            job_id=job_id,
            model=model,
            ai_model=ai_model,
            page_count=len(pages),
            output_characters=len(markdown),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            failed_pages=failed_pages or [],
            duration_ms=duration_ms,
            source_format=source_format,
            engine=engine,
            warnings=warnings or [],
        ),
        structure=StructureNode(id="document-1", type="document", children=page_nodes),
    )


def _assemble_atomic_grounding(
    lines: list[AtomicLineInput], markdown: str, global_start: int
) -> list[AtomicGrounding]:
    search_start = 0
    grounding: list[AtomicGrounding] = []
    for line in lines:
        local_start, local_end = _find_sequential(
            markdown,
            line.text,
            search_start,
            error="atomic grounding text must occur in its parent Markdown",
        )
        search_start = local_end
        grounding.append(
            AtomicGrounding(
                text=line.text,
                box=line.box,
                ranges=[
                    CodepointRange(start=global_start + local_start, end=global_start + local_end)
                ],
            )
        )
    return grounding


__all__ = [
    "AgenticBlockInput",
    "AgenticPageInput",
    "AtomicGrounding",
    "AtomicLineInput",
    "BlockType",
    "CodepointRange",
    "NormalizedBox",
    "ParseMetadata",
    "ParseResponse",
    "ParserEngine",
    "StructureNode",
    "assemble_parse_response",
]
