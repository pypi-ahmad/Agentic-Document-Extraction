"""Stateless orchestration for one document parse request."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from typing import Any, Literal

from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    BlockType,
    NormalizedBox,
    ParserEngine,
    ParseResponse,
    assemble_parse_response,
)
from paperplane.docling_parser import DoclingDocumentParser
from paperplane.ingest import OFFICE_EXTENSIONS, DocumentInputError, inspect_document, render_page
from paperplane.pipeline import PageResult, V2PageProcessor
from paperplane.pipeline_contracts import ProcessingMode, mode_policy
from paperplane.recipe import RecipeVersion

DEFAULT_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_DOCUMENT_PAGES = 500
DEFAULT_RECIPE_VERSION: RecipeVersion = "v9"

MODEL_MODES: dict[str, ProcessingMode] = {
    "paperplane-ade-fast-latest": ProcessingMode.ECONOMY,
    "paperplane-ade-latest": ProcessingMode.BALANCED,
    "paperplane-ade-audit-latest": ProcessingMode.AUDIT,
}

_BLOCK_TYPE_MAP: dict[str, tuple[BlockType, str | None]] = {
    "title": ("text", "title"),
    "heading": ("text", "heading"),
    "text": ("text", None),
    "list": ("text", "list"),
    "checkbox": ("text", "checkbox"),
    "table": ("table", None),
    "table_cell": ("text", "table_cell"),
    "form_field": ("text", "form_field"),
    "figure": ("figure", None),
    "chart": ("figure", "chart"),
    "header": ("marginalia", "header"),
    "footer": ("marginalia", "footer"),
}


def _normalised_box(chunk: Any) -> NormalizedBox:
    if chunk.grounding:
        box = chunk.grounding[0].box
        return NormalizedBox(left=box.left, top=box.top, right=box.right, bottom=box.bottom)
    return NormalizedBox(left=0, top=0, right=1, bottom=1)


def _atomic_lines(markdown: str, box: NormalizedBox) -> list[AtomicLineInput]:
    return [AtomicLineInput(text=line, box=box) for line in markdown.splitlines() if line.strip()]


def _agentic_page(result: PageResult, *, parser: ParserEngine) -> AgenticPageInput:
    chunks = sorted(result.chunks, key=lambda item: item.order)
    children_by_parent: dict[str, list[Any]] = {}
    for chunk in chunks:
        if chunk.type == "table_cell" and chunk.parent_id:
            children_by_parent.setdefault(chunk.parent_id, []).append(chunk)

    blocks: list[AgenticBlockInput] = []
    nested_ids: set[str] = set()
    for chunk in chunks:
        if chunk.id in nested_ids:
            continue
        block_type, semantic_role = _BLOCK_TYPE_MAP[chunk.type]
        box = _normalised_box(chunk)
        atomic_lines = [
            AtomicLineInput(
                text=line.text,
                box=NormalizedBox(
                    left=line.box.left,
                    top=line.box.top,
                    right=line.box.right,
                    bottom=line.box.bottom,
                ),
            )
            for line in chunk.atomic_lines
            if line.text in chunk.markdown
        ] or _atomic_lines(chunk.markdown, box)
        table_cells: list[AgenticBlockInput] = []
        if block_type == "table":
            cursor = 0
            for cell_index, cell in enumerate(children_by_parent.get(chunk.id, [])):
                start = chunk.markdown.find(cell.markdown, cursor)
                if start < 0:
                    continue
                cursor = start + len(cell.markdown)
                nested_ids.add(cell.id)
                cell_box = _normalised_box(cell)
                table_cells.append(
                    AgenticBlockInput(
                        type="table_cell",
                        markdown=cell.markdown,
                        box=cell_box,
                        grounding_status="grounded",
                        atomic_lines=[
                            AtomicLineInput(
                                text=line.text,
                                box=NormalizedBox(
                                    left=line.box.left,
                                    top=line.box.top,
                                    right=line.box.right,
                                    bottom=line.box.bottom,
                                ),
                            )
                            for line in cell.atomic_lines
                            if line.text in cell.markdown
                        ]
                        or _atomic_lines(cell.markdown, cell_box),
                        row=cell.row if cell.row is not None else 0,
                        col=cell.col if cell.col is not None else cell_index,
                        rowspan=cell.rowspan,
                        colspan=cell.colspan,
                    )
                )
        blocks.append(
            AgenticBlockInput(
                type=block_type,
                markdown=chunk.markdown,
                box=box,
                grounding_status="grounded",
                semantic_role=semantic_role,
                atomic_lines=atomic_lines,
                table_cells=table_cells,
            )
        )
    return AgenticPageInput(
        page_number=result.page_number,
        parser=parser,
        blocks=blocks,
    )


class AgenticDocumentParser:
    """Process every page immediately and return one grounded response."""

    def __init__(
        self,
        processor: V2PageProcessor,
        docling_parser: DoclingDocumentParser,
        *,
        vision_enabled: bool,
        vision_key_name: str = "OPENAI_API_KEY",
        vision_parser: ParserEngine = "openai_vision",
        max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
        max_document_pages: int = DEFAULT_MAX_DOCUMENT_PAGES,
        recipe_version: RecipeVersion = DEFAULT_RECIPE_VERSION,
    ) -> None:
        self.processor = processor
        self.docling_parser = docling_parser
        self.vision_enabled = vision_enabled
        self.vision_key_name = vision_key_name
        self.vision_parser: ParserEngine = vision_parser
        self.max_upload_bytes = max_upload_bytes
        self.max_document_pages = max_document_pages
        self.recipe_version: RecipeVersion = recipe_version

    async def parse(self, *, data: bytes, filename: str, model: str) -> ParseResponse:
        inspected = inspect_document(
            data,
            filename,
            self.max_upload_bytes,
            self.max_document_pages,
        )
        mode = MODEL_MODES[model]
        policy = mode_policy(mode)
        source_sha256 = hashlib.sha256(data).hexdigest()
        started = time.monotonic()
        pages: dict[int | None, AgenticPageInput] = {}
        warnings: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cached_input_tokens = 0
        cache_write_tokens = 0

        async def describe_figure(image_png: bytes, caption: str) -> str:
            nonlocal input_tokens, output_tokens, cached_input_tokens, cache_write_tokens
            description, usage = await self.processor.describe_figure_with_usage(
                image_png,
                caption,
                mode=mode,
            )
            input_tokens += usage.input_tokens
            output_tokens += usage.output_tokens
            cached_input_tokens += usage.cached_input_tokens
            cache_write_tokens += usage.cache_write_tokens
            return description

        suffix = filename.lower().rsplit(".", 1)[-1]
        is_office = f".{suffix}" in OFFICE_EXTENSIONS
        if is_office or inspected.native_pages:
            docling_result = await self.docling_parser.parse(
                data=data,
                filename=filename,
                max_bytes=self.max_upload_bytes,
                max_pages=self.max_document_pages,
                requested_pages=set(inspected.native_pages) if inspected.native_pages else None,
                describe_figure=describe_figure if self.vision_enabled else None,
            )
            pages.update(docling_result.pages)
            warnings.extend(docling_result.warnings)

        vision_pages = inspected.vision_pages
        if vision_pages and not self.vision_enabled:
            raise DocumentInputError(
                "missing_api_key",
                f"{self.vision_key_name} is required for scanned PDF pages and image files",
            )
        for page_number in vision_pages:
            rendered = await asyncio.to_thread(
                render_page,
                data,
                filename,
                page_number,
                policy.base_dpi,
            )
            result = await self.processor.process_page(
                source=data,
                filename=filename,
                source_sha256=source_sha256,
                page=rendered,
                mode=mode,
                recipe_version=self.recipe_version,
            )
            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            cached_input_tokens += result.cached_input_tokens
            cache_write_tokens += result.cache_write_tokens
            pages[page_number] = _agentic_page(result, parser=self.vision_parser)

        if not pages:
            raise DocumentInputError("empty_document", "Document produced no readable pages")

        ordered_pages = [pages[key] for key in sorted(pages, key=lambda item: item or 0)]
        engines = {page.parser for page in ordered_pages}
        engine: Literal[
            "docling",
            "openai_vision",
            "xai_vision",
            "google_vision",
            "anthropic_vision",
            "agnes_vision",
            "hybrid",
        ] = (
            "hybrid"
            if len(engines) > 1
            else "docling"
            if engines == {"docling"}
            else self.vision_parser
        )

        request_id = uuid.uuid4().hex
        return assemble_parse_response(
            document_id=request_id,
            job_id=request_id,
            model=model,
            ai_model=self.processor.model,
            pages=ordered_pages,
            duration_ms=round((time.monotonic() - started) * 1000),
            source_format=inspected.source_format,
            engine=engine,
            warnings=warnings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
        )


__all__ = [
    "DEFAULT_MAX_DOCUMENT_PAGES",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "MODEL_MODES",
    "AgenticDocumentParser",
]
