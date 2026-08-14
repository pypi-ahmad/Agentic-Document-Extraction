"""Adapter from Firecrawl PDF Inspector into Paperplane page inputs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import fitz
import pdf_inspector

from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    NormalizedBox,
)
from paperplane.ingest import DocumentInputError


@dataclass(frozen=True)
class PdfInspectorParseResult:
    pages: dict[int, AgenticPageInput]
    confidence: float
    pdf_type: str
    pages_needing_ocr: list[int]
    warnings: list[str]


def parse_pdf_with_inspector(
    data: bytes, selected_pages: tuple[int, ...]
) -> PdfInspectorParseResult:
    """Extract selected PDF pages without OCR or network access."""

    try:
        summary = pdf_inspector.process_pdf_bytes(data, pages=list(selected_pages))
        extracted = pdf_inspector.extract_pages_markdown_bytes(
            data, pages=[page - 1 for page in selected_pages]
        )
        positioned = pdf_inspector.extract_text_with_positions_bytes(
            data, pages=list(selected_pages)
        )
    except Exception as exc:
        raise DocumentInputError(
            "pdf_inspector_failed", "PDF Inspector could not process this PDF"
        ) from exc

    items_by_page: dict[int, list[Any]] = defaultdict(list)
    for item in positioned:
        items_by_page[int(item.page)].append(item)

    document = fitz.open(stream=data, filetype="pdf")
    try:
        extracted_by_page = {int(page.page) + 1: page for page in extracted.pages}
        pages: dict[int, AgenticPageInput] = {}
        for page_number in selected_pages:
            page_result = extracted_by_page.get(page_number)
            markdown = str(getattr(page_result, "markdown", "") or "").strip()
            blocks: list[AgenticBlockInput] = []
            if markdown:
                items = items_by_page.get(page_number, [])
                page_rect = document[page_number - 1].rect
                box = _items_box(items, float(page_rect.width), float(page_rect.height))
                blocks.append(
                    AgenticBlockInput(
                        type="text",
                        markdown=markdown,
                        box=box,
                        grounding_status="grounded" if box is not None else "semantic_only",
                        semantic_role="pdf_inspector_markdown",
                        atomic_lines=_atomic_lines(
                            markdown,
                            items,
                            float(page_rect.width),
                            float(page_rect.height),
                        ),
                    )
                )
            pages[page_number] = AgenticPageInput(
                page_number=page_number,
                parser="pdf_inspector",
                blocks=blocks,
            )
    finally:
        document.close()

    warnings: list[str] = []
    pages_needing_ocr = sorted(page for page in summary.pages_needing_ocr if page in selected_pages)
    if pages_needing_ocr:
        warnings.append("PDF Inspector cannot OCR pages: " + ", ".join(map(str, pages_needing_ocr)))
    if bool(summary.has_encoding_issues):
        warnings.append("PDF Inspector detected unreliable font encoding")
    return PdfInspectorParseResult(
        pages=pages,
        confidence=float(summary.confidence),
        pdf_type=str(summary.pdf_type),
        pages_needing_ocr=pages_needing_ocr,
        warnings=warnings,
    )


def _items_box(items: list[Any], width: float, height: float) -> NormalizedBox | None:
    boxes = [_item_box(item, width, height) for item in items]
    valid = [box for box in boxes if box is not None]
    if not valid:
        return None
    return NormalizedBox(
        left=min(box.left for box in valid),
        top=min(box.top for box in valid),
        right=max(box.right for box in valid),
        bottom=max(box.bottom for box in valid),
    )


def _item_box(item: Any, width: float, height: float) -> NormalizedBox | None:
    if width <= 0 or height <= 0:
        return None
    left = max(0.0, min(float(item.x) / width, 1.0))
    # PDF Inspector exposes PDF-space coordinates with a bottom-left origin.
    top = max(0.0, min((height - float(item.y) - float(item.height)) / height, 1.0))
    right = max(0.0, min((float(item.x) + float(item.width)) / width, 1.0))
    bottom = max(0.0, min((height - float(item.y)) / height, 1.0))
    if right <= left or bottom <= top:
        return None
    return NormalizedBox(left=left, top=top, right=right, bottom=bottom)


def _atomic_lines(
    markdown: str, items: list[Any], width: float, height: float
) -> list[AtomicLineInput]:
    cursor = 0
    lines: list[AtomicLineInput] = []
    for item in items:
        text = str(item.text).strip()
        box = _item_box(item, width, height)
        if not text or box is None:
            continue
        start = markdown.find(text, cursor)
        if start < 0:
            continue
        cursor = start + len(text)
        lines.append(AtomicLineInput(text=text, box=box))
    return lines


__all__ = ["PdfInspectorParseResult", "parse_pdf_with_inspector"]
