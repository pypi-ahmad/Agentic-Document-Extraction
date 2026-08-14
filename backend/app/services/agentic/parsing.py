"""Stateless orchestration for one document parse request."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from typing import Any

from app.config import settings
from app.services.agentic.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    BlockType,
    NormalizedBox,
    ParseResponse,
    assemble_parse_response,
)
from app.services.parsing.ingest import inspect_document, render_page
from app.services.parsing.v2_contracts import ProcessingMode, mode_policy
from app.services.parsing.v2_pipeline import PageResult, V2PageProcessor

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


def _agentic_page(result: PageResult) -> AgenticPageInput:
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
                        atomic_lines=_atomic_lines(cell.markdown, cell_box),
                        row=0,
                        col=cell_index,
                    )
                )
        blocks.append(
            AgenticBlockInput(
                type=block_type,
                markdown=chunk.markdown,
                box=box,
                semantic_role=semantic_role,
                atomic_lines=_atomic_lines(chunk.markdown, box),
                table_cells=table_cells,
            )
        )
    return AgenticPageInput(page_number=result.page_number, blocks=blocks)


class AgenticDocumentParser:
    """Process every page immediately and return one grounded response."""

    def __init__(self, processor: V2PageProcessor) -> None:
        self.processor = processor

    async def parse(self, *, data: bytes, filename: str, model: str) -> ParseResponse:
        inspected = inspect_document(
            data,
            filename,
            settings.max_upload_bytes,
            settings.max_document_pages,
        )
        mode = MODEL_MODES[model]
        policy = mode_policy(mode)
        source_sha256 = hashlib.sha256(data).hexdigest()
        started = time.monotonic()
        page_results: list[PageResult] = []
        for page_number in range(1, inspected.page_count + 1):
            rendered = await asyncio.to_thread(
                render_page,
                data,
                filename,
                page_number,
                policy.base_dpi,
            )
            page_results.append(
                await self.processor.process_page(
                    source=data,
                    filename=filename,
                    source_sha256=source_sha256,
                    page=rendered,
                    mode=mode,
                    recipe_version=settings.v2_recipe_version,
                )
            )

        request_id = uuid.uuid4().hex
        return assemble_parse_response(
            document_id=request_id,
            job_id=request_id,
            model=model,
            pages=[_agentic_page(result) for result in page_results],
            duration_ms=round((time.monotonic() - started) * 1000),
        )


__all__ = ["MODEL_MODES", "AgenticDocumentParser"]
