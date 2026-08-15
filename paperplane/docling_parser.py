"""Local Docling conversion into Paperplane's deterministic parse inputs."""

# Docling reads its cache location while its modules are imported.
# ruff: noqa: E402

from __future__ import annotations

import asyncio
import html
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from io import BytesIO
from typing import Any

from paperplane.model_store import ModelStore

ModelStore().configure_environment()

from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import DocumentStream, InputFormat
from docling.datamodel.object_detection_engine_options import (
    TransformersObjectDetectionEngineOptions,
)
from docling.datamodel.pipeline_options import (
    LayoutObjectDetectionOptions,
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.transforms.serializer.html import HTMLTableSerializer
from docling_core.transforms.serializer.markdown import MarkdownDocSerializer, MarkdownParams
from docling_core.types.doc.document import DoclingDocument
from docling_core.types.doc.items.node import DocItem
from docling_core.types.doc.items.picture.picture import PictureItem
from docling_core.types.doc.items.table.table import TableItem

from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    GroundingStatus,
    NormalizedBox,
)
from paperplane.ingest import DocumentInputError

FigureDescriber = Callable[[bytes, str], Awaitable[str]]

DOCLING_FORMATS = {
    ".pdf": InputFormat.PDF,
    ".docx": InputFormat.DOCX,
    ".pptx": InputFormat.PPTX,
    ".xlsx": InputFormat.XLSX,
    ".odt": InputFormat.ODT,
    ".odp": InputFormat.ODP,
    ".ods": InputFormat.ODS,
    ".csv": InputFormat.CSV,
    ".png": InputFormat.IMAGE,
    ".jpg": InputFormat.IMAGE,
    ".jpeg": InputFormat.IMAGE,
    ".webp": InputFormat.IMAGE,
    ".tif": InputFormat.IMAGE,
    ".tiff": InputFormat.IMAGE,
    ".bmp": InputFormat.IMAGE,
}


@dataclass(frozen=True)
class DoclingParseResult:
    pages: dict[int | None, AgenticPageInput]
    warnings: list[str]
    page_confidence: dict[int, float | None]


def create_docling_converter(
    device: AcceleratorDevice | str = AcceleratorDevice.AUTO,
) -> DocumentConverter:
    """Create the local converter with RapidOCR and remote plugins disabled."""
    pdf_options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        generate_picture_images=True,
        images_scale=2.0,
        enable_remote_services=False,
        allow_external_plugins=False,
        accelerator_options=AcceleratorOptions(device=device),
        ocr_options=RapidOcrOptions(backend="torch"),
        table_structure_options=TableStructureOptions(
            mode=TableFormerMode.ACCURATE,
            do_cell_matching=True,
        ),
        layout_options=LayoutObjectDetectionOptions(
            engine_options=TransformersObjectDetectionEngineOptions(compile_model=False)
        ),
    )
    return DocumentConverter(
        allowed_formats=list(DOCLING_FORMATS.values()),
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options)},
    )


class DoclingDocumentParser:
    def __init__(
        self,
        converter: DocumentConverter,
        fallback_converter: DocumentConverter | None = None,
    ) -> None:
        self.converter = converter
        self.fallback_converter = fallback_converter

    async def parse(
        self,
        *,
        data: bytes,
        filename: str,
        max_bytes: int,
        max_pages: int,
        requested_pages: set[int] | None = None,
        describe_figure: FigureDescriber | None = None,
    ) -> DoclingParseResult:
        page_range = (
            (min(requested_pages), max(requested_pages)) if requested_pages else (1, max_pages)
        )
        warnings: list[str] = []
        try:
            conversion = await self._convert(
                self.converter,
                data=data,
                filename=filename,
                max_bytes=max_bytes,
                max_pages=max_pages,
                page_range=page_range,
            )
        except Exception as primary_error:
            if self.fallback_converter is None:
                raise DocumentInputError(
                    "conversion_failed", "Docling could not convert this document"
                ) from primary_error
            try:
                conversion = await self._convert(
                    self.fallback_converter,
                    data=data,
                    filename=filename,
                    max_bytes=max_bytes,
                    max_pages=max_pages,
                    page_range=page_range,
                )
                warnings.append("Docling retried on CPU after a CUDA conversion failure")
            except Exception as fallback_error:
                raise DocumentInputError(
                    "conversion_failed", "Docling could not convert this document"
                ) from fallback_error

        document = conversion.document
        physical_pages = sorted(int(page) for page in document.pages)
        page_numbers: list[int | None] = []
        if requested_pages is not None:
            page_numbers.extend(sorted(requested_pages))
        elif physical_pages:
            page_numbers.extend(physical_pages)
        else:
            page_numbers = [None]

        pages: dict[int | None, AgenticPageInput] = {}
        for page_number in page_numbers:
            blocks = await self._blocks_for_page(
                document,
                page_number,
                describe_figure=describe_figure,
                warnings=warnings,
            )
            pages[page_number] = AgenticPageInput(
                page_number=page_number,
                parser="docling",
                blocks=blocks,
            )
        confidence_pages = getattr(getattr(conversion, "confidence", None), "pages", {})
        page_confidence = {
            page_number: _minimum_page_confidence(confidence_pages.get(page_number))
            for page_number in page_numbers
            if page_number is not None
        }
        return DoclingParseResult(
            pages=pages,
            warnings=warnings,
            page_confidence=page_confidence,
        )

    async def _convert(
        self,
        converter: DocumentConverter,
        *,
        data: bytes,
        filename: str,
        max_bytes: int,
        max_pages: int,
        page_range: tuple[int, int],
    ) -> Any:
        return await asyncio.to_thread(
            converter.convert,
            DocumentStream(name=filename, stream=BytesIO(data)),
            max_file_size=max_bytes,
            max_num_pages=max_pages,
            page_range=page_range,
        )

    async def _blocks_for_page(
        self,
        document: DoclingDocument,
        page_number: int | None,
        *,
        describe_figure: FigureDescriber | None,
        warnings: list[str],
    ) -> list[AgenticBlockInput]:
        params = MarkdownParams(
            pages={page_number} if page_number is not None else None,
            escape_html=False,
            image_placeholder="<!-- image -->",
        )
        serializer = MarkdownDocSerializer(
            doc=document,
            table_serializer=HTMLTableSerializer(),
            params=params,
        )
        blocks: list[AgenticBlockInput] = []
        for item, _level in document.iterate_items(
            traverse_pictures=True,
            page_no=page_number,
        ):
            if not isinstance(item, DocItem):
                continue
            table = item if isinstance(item, TableItem) else None
            picture = item if isinstance(item, PictureItem) else None
            markdown = serializer.serialize(item=item).text.strip()
            if picture is not None:
                markdown = await self._figure_markdown(
                    document,
                    picture,
                    describe_figure=describe_figure,
                    warnings=warnings,
                )
            if not markdown:
                continue

            box = _items_box(document, [item], page_number)
            grounding_status: GroundingStatus = "grounded" if box is not None else "semantic_only"
            block_type = (
                "table" if table is not None else "figure" if picture is not None else "text"
            )
            semantic_role = _semantic_role([item])
            cells = _table_cells(document, table, page_number) if table is not None else []
            blocks.append(
                AgenticBlockInput(
                    type=block_type,
                    markdown=markdown,
                    box=box,
                    grounding_status=grounding_status,
                    semantic_role=semantic_role,
                    atomic_lines=_atomic_lines(markdown, box) if table is None else [],
                    table_cells=cells,
                )
            )
        return blocks

    async def _figure_markdown(
        self,
        document: DoclingDocument,
        picture: PictureItem,
        *,
        describe_figure: FigureDescriber | None,
        warnings: list[str],
    ) -> str:
        caption = picture.caption_text(document).strip()
        image = await asyncio.to_thread(picture.get_image, document)
        if describe_figure is not None and image is not None:
            output = BytesIO()
            image.convert("RGB").save(output, format="PNG")
            try:
                return await describe_figure(output.getvalue(), caption)
            except Exception:
                if "figure_description_unavailable" not in warnings:
                    warnings.append("figure_description_unavailable")
        caption_markup = f"\n{html.escape(caption)}" if caption else ""
        return (
            '<figure type="FIGURE"><description>Visual content present; '
            f"description unavailable.</description>{caption_markup}</figure>"
        )


def _semantic_role(items: list[DocItem]) -> str | None:
    for item in items:
        label = getattr(item, "label", None)
        value = getattr(label, "value", None)
        if value:
            return str(value)
    return None


def _items_box(
    document: DoclingDocument, items: list[DocItem], page_number: int | None
) -> NormalizedBox | None:
    boxes = [
        box
        for item in items
        for provenance in item.prov
        if page_number is None or provenance.page_no == page_number
        if (box := _normalized_docling_box(document, provenance.page_no, provenance.bbox))
        is not None
    ]
    if not boxes:
        return None
    return NormalizedBox(
        left=min(box.left for box in boxes),
        top=min(box.top for box in boxes),
        right=max(box.right for box in boxes),
        bottom=max(box.bottom for box in boxes),
    )


def _normalized_docling_box(
    document: DoclingDocument, page_number: int, source_box: Any
) -> NormalizedBox | None:
    page = document.pages.get(page_number)
    if page is None or page.size.width <= 0 or page.size.height <= 0:
        return None
    box = source_box.to_top_left_origin(page_height=page.size.height).normalized(page.size)
    left = max(0.0, min(float(box.l), 1.0))
    top = max(0.0, min(float(box.t), 1.0))
    right = max(0.0, min(float(box.r), 1.0))
    bottom = max(0.0, min(float(box.b), 1.0))
    if right <= left or bottom <= top:
        return None
    return NormalizedBox(left=left, top=top, right=right, bottom=bottom)


def _table_cells(
    document: DoclingDocument, table: TableItem, page_number: int | None
) -> list[AgenticBlockInput]:
    parent_page = table.prov[0].page_no if table.prov else page_number
    cells: list[AgenticBlockInput] = []
    for cell in table.data.table_cells:
        box = (
            _normalized_docling_box(document, parent_page, cell.bbox)
            if parent_page is not None and cell.bbox is not None
            else None
        )
        cells.append(
            AgenticBlockInput(
                type="table_cell",
                markdown=html.escape(cell.text, quote=False),
                box=box,
                grounding_status="grounded" if box is not None else "semantic_only",
                atomic_lines=[AtomicLineInput(text=html.escape(cell.text, quote=False), box=box)]
                if box is not None and cell.text
                else [],
                row=cell.start_row_offset_idx,
                col=cell.start_col_offset_idx,
                rowspan=cell.row_span,
                colspan=cell.col_span,
            )
        )
    return cells


def _atomic_lines(markdown: str, box: NormalizedBox | None) -> list[AtomicLineInput]:
    if box is None:
        return []
    return [AtomicLineInput(text=line, box=box) for line in markdown.splitlines() if line.strip()]


def _minimum_page_confidence(report: Any) -> float | None:
    if report is None:
        return None
    values: list[float] = []
    for name in ("parse_score", "layout_score", "ocr_score"):
        raw = getattr(report, name, None)
        if raw is None:
            continue
        value = float(raw)
        if math.isfinite(value):
            values.append(value)
    return min(values) if values else None


__all__ = [
    "DOCLING_FORMATS",
    "DoclingDocumentParser",
    "DoclingParseResult",
    "create_docling_converter",
]
