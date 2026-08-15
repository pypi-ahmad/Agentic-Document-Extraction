"""Stateless orchestration for one document parse request."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import Callable
from typing import Any, Literal

from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    BlockType,
    CodepointRange,
    GroundedWord,
    ModelTokenUsage,
    NormalizedBox,
    ParserEngine,
    ParseResponse,
    ProcessingStrategy,
    assemble_parse_response,
)
from paperplane.docling_parser import DoclingDocumentParser
from paperplane.ingest import (
    OFFICE_EXTENSIONS,
    DocumentInputError,
    extract_native_words,
    extract_ocr_words,
    inspect_document,
    render_page,
    select_page_range,
)
from paperplane.office import convert_office_to_pdf
from paperplane.pdf_inspector_parser import PdfInspectorParseResult, parse_pdf_with_inspector
from paperplane.pipeline import PageResult, V2PageProcessor
from paperplane.pipeline_contracts import ProcessingMode, mode_policy
from paperplane.recipe import RecipeVersion

DEFAULT_MAX_UPLOAD_BYTES = 200 * 1024 * 1024
DEFAULT_MAX_DOCUMENT_PAGES = 500
DEFAULT_RECIPE_VERSION: RecipeVersion = "v9"
REFINEMENT_CONFIDENCE_THRESHOLD = 0.80

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
        docling_parser: DoclingDocumentParser | None,
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

    async def parse(
        self,
        *,
        data: bytes,
        filename: str,
        model: str,
        strategy: ProcessingStrategy = "ai",
        page_start: int = 1,
        page_end: int | None = None,
        progress_callback: Callable[[int], None] | None = None,
    ) -> ParseResponse:
        original_suffix = filename.lower().rsplit(".", 1)[-1]
        original_format = original_suffix if "." in filename else "unknown"
        if strategy.startswith("pdf_inspector") and original_format != "pdf":
            raise DocumentInputError(
                "pdf_required", "PDF Inspector strategies only accept PDF files"
            )

        working_data = data
        working_filename = filename
        if f".{original_suffix}" in OFFICE_EXTENSIONS:
            working_data = await asyncio.to_thread(
                convert_office_to_pdf,
                data,
                filename,
                max_bytes=self.max_upload_bytes,
            )
            working_filename = f"{filename.rsplit('.', 1)[0]}.pdf"

        inspected = await asyncio.to_thread(
            inspect_document,
            working_data,
            working_filename,
            self.max_upload_bytes,
            self.max_document_pages,
        )
        selected_pages = select_page_range(inspected.page_count, page_start, page_end)
        selected_page_set = set(selected_pages)
        if (
            strategy
            in {
                "ai",
                "docling_ai",
                "pdf_inspector_ai",
                "ollama",
                "ollama_ai",
            }
            and not self.vision_enabled
        ):
            raise DocumentInputError(
                "missing_api_key", f"{self.vision_key_name} is required for this AI strategy"
            )

        mode = MODEL_MODES[model]
        policy = mode_policy(mode)
        source_sha256 = hashlib.sha256(working_data).hexdigest()
        started = time.monotonic()
        pages: dict[int | None, AgenticPageInput] = {}
        warnings: list[str] = []
        input_tokens = 0
        output_tokens = 0
        cached_input_tokens = 0
        cache_write_tokens = 0
        model_usage: dict[str, ModelTokenUsage] = {}
        reported_pages: set[int] = set()

        def report_page_complete(page_number: int) -> None:
            if progress_callback is None or page_number in reported_pages:
                return
            reported_pages.add(page_number)
            progress_callback(page_number)

        docling_confidence: dict[int, float | None] = {}
        inspector_result: PdfInspectorParseResult | None = None
        if strategy in {"docling", "docling_ai"}:
            if self.docling_parser is None:
                raise RuntimeError("Docling strategy requires a Docling parser")
            try:
                docling_result = await self.docling_parser.parse(
                    data=working_data,
                    filename=working_filename,
                    max_bytes=self.max_upload_bytes,
                    max_pages=self.max_document_pages,
                    requested_pages=selected_page_set,
                    describe_figure=None,
                )
                pages.update(docling_result.pages)
                warnings.extend(docling_result.warnings)
                docling_confidence = docling_result.page_confidence
            except DocumentInputError:
                if strategy == "docling":
                    raise
                warnings.append("Docling failed; AI processed the selected pages")

        if strategy in {"pdf_inspector", "pdf_inspector_ai"}:
            try:
                inspector_result = await asyncio.to_thread(
                    parse_pdf_with_inspector, working_data, selected_pages
                )
                for page_number, page in inspector_result.pages.items():
                    pages[page_number] = page
                warnings.extend(inspector_result.warnings)
            except DocumentInputError:
                if strategy == "pdf_inspector":
                    raise
                warnings.append("PDF Inspector failed; AI processed the selected pages")

        ai_pages: tuple[int, ...] = ()
        if strategy in {"ai", "ollama", "ollama_ai"}:
            ai_pages = selected_pages
        elif strategy == "docling_ai":
            pages_to_refine: list[int] = []
            for page_number in selected_pages:
                confidence = docling_confidence.get(page_number)
                page = pages.get(page_number)
                if (
                    confidence is None
                    or confidence < REFINEMENT_CONFIDENCE_THRESHOLD
                    or page is None
                    or not page.blocks
                ):
                    pages_to_refine.append(page_number)
            ai_pages = tuple(pages_to_refine)
        elif strategy == "pdf_inspector_ai":
            if inspector_result is None or (
                inspector_result.confidence < REFINEMENT_CONFIDENCE_THRESHOLD
            ):
                ai_pages = selected_pages
            else:
                ai_pages = tuple(
                    page_number
                    for page_number in selected_pages
                    if page_number in inspector_result.pages_needing_ocr
                    or not pages.get(page_number)
                    or not pages[page_number].blocks
                )

        for page_number in selected_pages:
            if page_number not in ai_pages:
                report_page_complete(page_number)

        refined_pages: list[int] = []
        for page_number in ai_pages:
            rendered = await asyncio.to_thread(
                render_page,
                working_data,
                working_filename,
                page_number,
                policy.base_dpi,
            )
            local_page = pages.get(page_number)
            current_context = _page_context(local_page)
            preceding_context = "\n\n".join(
                context
                for prior_page in selected_pages
                if prior_page < page_number
                and (context := _page_context(pages.get(prior_page))) is not None
            )
            context_parts = [part for part in (preceding_context[-6000:], current_context) if part]
            context = "\n\n".join(context_parts) or None
            try:
                result = await self.processor.process_page(
                    source=working_data,
                    filename=working_filename,
                    source_sha256=source_sha256,
                    page=rendered,
                    mode=mode,
                    recipe_version=self.recipe_version,
                    context=context,
                )
            except Exception:
                if (
                    strategy in {"ai", "ollama", "ollama_ai"}
                    or local_page is None
                    or not local_page.blocks
                ):
                    raise
                warnings.append(f"AI refinement failed for page {page_number}; local output kept")
                report_page_complete(page_number)
                continue
            input_tokens += result.input_tokens
            output_tokens += result.output_tokens
            cached_input_tokens += result.cached_input_tokens
            cache_write_tokens += result.cache_write_tokens
            page_model_usage = result.model_usage or {
                self.processor.model: ModelTokenUsage(
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cached_input_tokens=result.cached_input_tokens,
                    cache_write_tokens=result.cache_write_tokens,
                )
            }
            for model_id, usage in page_model_usage.items():
                aggregate = model_usage.setdefault(model_id, ModelTokenUsage())
                aggregate.input_tokens += usage.input_tokens
                aggregate.output_tokens += usage.output_tokens
                aggregate.cached_input_tokens += usage.cached_input_tokens
                aggregate.cache_write_tokens += usage.cache_write_tokens
            warnings.extend(f"Page {page_number}: {warning}" for warning in result.warnings)
            pages[page_number] = _agentic_page(result, parser=self.vision_parser)
            refined_pages.append(page_number)
            report_page_complete(page_number)

        if not pages:
            raise DocumentInputError("empty_document", "Document produced no readable pages")

        for page_number in selected_pages:
            pages.setdefault(
                page_number,
                AgenticPageInput(
                    page_number=page_number,
                    parser=("pdf_inspector" if strategy.startswith("pdf_inspector") else "docling"),
                ),
            )
            report_page_complete(page_number)
        ordered_pages = [pages[page_number] for page_number in selected_pages]
        engines = {page.parser for page in ordered_pages}
        engine: Literal[
            "docling",
            "pdf_inspector",
            "openai_vision",
            "xai_vision",
            "google_vision",
            "anthropic_vision",
            "agnes_vision",
            "ollama_vision",
            "hybrid",
        ] = (
            "hybrid"
            if len(engines) > 1
            else "docling"
            if engines == {"docling"}
            else "pdf_inspector"
            if engines == {"pdf_inspector"}
            else self.vision_parser
        )

        failed_pages = [page.page_number for page in ordered_pages if not page.blocks]

        request_id = uuid.uuid4().hex
        response = assemble_parse_response(
            document_id=request_id,
            job_id=request_id,
            model=model,
            ai_model=(
                self.processor.model
                if strategy in {"ai", "docling_ai", "pdf_inspector_ai", "ollama", "ollama_ai"}
                else None
            ),
            pages=ordered_pages,
            failed_pages=[page for page in failed_pages if page is not None],
            duration_ms=round((time.monotonic() - started) * 1000),
            source_format=original_format,
            processing_strategy=strategy,
            source_page_count=inspected.page_count,
            page_range=(selected_pages[0], selected_pages[-1]),
            ai_refined_pages=refined_pages,
            pdf_type=inspector_result.pdf_type if inspector_result else None,
            pdf_inspector_confidence=(inspector_result.confidence if inspector_result else None),
            pages_needing_ocr=(inspector_result.pages_needing_ocr if inspector_result else []),
            engine=engine,
            warnings=warnings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            cache_write_tokens=cache_write_tokens,
            model_usage=model_usage,
        )
        response.words = await asyncio.to_thread(
            _word_grounding,
            response,
            working_data,
            working_filename,
            selected_pages,
        )
        return response


def _page_context(page: AgenticPageInput | None) -> str | None:
    if page is None:
        return None
    markdown = "\n\n".join(block.markdown for block in page.blocks if block.markdown).strip()
    return markdown or None


def _word_grounding(
    response: ParseResponse,
    data: bytes,
    filename: str,
    selected_pages: tuple[int, ...],
) -> list[GroundedWord]:
    grounded: list[GroundedWord] = []
    for page_number, page_node in zip(selected_pages, response.structure.children, strict=True):
        ranges = [item for block in page_node.children for item in block.ranges]
        if not ranges:
            continue
        page_start = min(item.start for item in ranges)
        page_end = max(item.end for item in ranges)
        cursor = page_start
        observed = [
            (word, 1.0, "native_pdf") for word in extract_native_words(data, filename, page_number)
        ]
        if not observed:
            rendered = render_page(data, filename, page_number, 150)
            observed = [
                (word, confidence, "local_ocr")
                for word, confidence in extract_ocr_words(rendered.image_png)
            ]
        for word, confidence, source in observed:
            start = response.markdown.find(word.text, cursor, page_end)
            if start < 0:
                continue
            end = start + len(word.text)
            cursor = end
            grounded.append(
                GroundedWord(
                    text=word.text,
                    page=page_number,
                    box=NormalizedBox(
                        left=word.bbox.left,
                        top=word.bbox.top,
                        right=word.bbox.right,
                        bottom=word.bbox.bottom,
                    ),
                    range=CodepointRange(start=start, end=end),
                    source=source,
                    raw_confidence=confidence,
                )
            )
    return grounded


__all__ = [
    "DEFAULT_MAX_DOCUMENT_PAGES",
    "DEFAULT_MAX_UPLOAD_BYTES",
    "MODEL_MODES",
    "AgenticDocumentParser",
]
