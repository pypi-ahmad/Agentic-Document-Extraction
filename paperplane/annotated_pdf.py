"""Build an in-memory PDF for reviewing Paperplane grounding evidence."""

from __future__ import annotations

import html
import re
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

import fitz
from PIL import Image

from paperplane.contracts import ParseResponse, StructureNode
from paperplane.ingest import IMAGE_EXTENSIONS

ArtifactKind = Literal["source_overlay", "semantic_report"]

_COLORS: dict[str, tuple[float, float, float]] = {
    "text": (0.10, 0.38, 0.88),
    "table": (0.00, 0.55, 0.62),
    "table_cell": (0.10, 0.60, 0.35),
    "figure": (0.93, 0.43, 0.10),
    "marginalia": (0.45, 0.49, 0.55),
}


@dataclass(frozen=True)
class AnnotatedPdfArtifact:
    data: bytes
    kind: ArtifactKind
    annotated_blocks: int
    semantic_blocks: int


def build_annotated_pdf(
    *, source: bytes, filename: str, response: ParseResponse
) -> AnnotatedPdfArtifact:
    """Overlay physical evidence or create an explicit semantic-only review report."""

    document = _source_document(source, filename)
    if document is None:
        return _semantic_report(response)

    annotated = 0
    semantic = 0
    try:
        for node in _content_nodes(response.structure):
            if node.box is None or node.page is None or node.page > document.page_count:
                semantic += 1
                continue
            page = document[node.page - 1]
            rectangle = fitz.Rect(
                node.box.left * page.rect.width,
                node.box.top * page.rect.height,
                node.box.right * page.rect.width,
                node.box.bottom * page.rect.height,
            )
            color = _COLORS.get(node.type, (0.55, 0.20, 0.65))
            page.draw_rect(
                rectangle,
                color=color,
                fill=color,
                width=1.0,
                fill_opacity=0.06,
                stroke_opacity=0.9,
                overlay=True,
            )
            page.insert_text(
                (rectangle.x0, max(page.rect.y0 + 7, rectangle.y0 - 2)),
                f"{node.id} | {node.type}",
                fontsize=6,
                color=color,
                overlay=True,
            )
            annotated += 1
        return AnnotatedPdfArtifact(
            data=document.tobytes(garbage=3, deflate=True),
            kind="source_overlay",
            annotated_blocks=annotated,
            semantic_blocks=semantic,
        )
    finally:
        document.close()


def _source_document(source: bytes, filename: str) -> fitz.Document | None:
    suffix = Path(filename).suffix.casefold()
    if suffix == ".pdf":
        return fitz.open(stream=source, filetype="pdf")
    if suffix not in IMAGE_EXTENSIONS:
        return None

    document = fitz.open()
    try:
        with Image.open(BytesIO(source)) as image:
            for frame_index in range(int(getattr(image, "n_frames", 1))):
                image.seek(frame_index)
                rgb = image.convert("RGB")
                scale = min(1.0, 14_000 / max(rgb.width, rgb.height))
                width = max(1.0, rgb.width * scale)
                height = max(1.0, rgb.height * scale)
                output = BytesIO()
                rgb.save(output, format="PNG")
                page = document.new_page(width=width, height=height)
                page.insert_image(page.rect, stream=output.getvalue())
        return document
    except Exception:
        document.close()
        raise


def _semantic_report(response: ParseResponse) -> AnnotatedPdfArtifact:
    document = fitz.open()
    try:
        return _populate_semantic_report(document, response)
    finally:
        document.close()


def _populate_semantic_report(
    document: fitz.Document, response: ParseResponse
) -> AnnotatedPdfArtifact:
    semantic = 0
    page = _new_report_page(document)
    y = 88.0

    for page_node in response.structure.children:
        page_label = f"Source page {page_node.page}" if page_node.page else "Logical document"
        if y > 745:
            page = _new_report_page(document)
            y = 88.0
        page.insert_text((40, y), page_label, fontsize=12, color=(0.08, 0.22, 0.42))
        y += 22
        for node in _content_nodes(page_node):
            semantic += 1
            excerpt = _plain_excerpt(node.text or "")
            lines = textwrap.wrap(excerpt, width=88)[:4] or ["(empty block)"]
            required_height = 28 + len(lines) * 12
            if y + required_height > 800:
                page = _new_report_page(document)
                y = 88.0
            color = _COLORS.get(node.type, (0.55, 0.20, 0.65))
            page.draw_rect(
                fitz.Rect(40, y - 10, 44, y + required_height - 16),
                color=color,
                fill=color,
                overlay=True,
            )
            page.insert_text(
                (52, y),
                _pdf_text(f"{node.id} | {node.type} | semantic_only"),
                fontsize=8,
                color=color,
            )
            y += 14
            for line in lines:
                page.insert_text((52, y), _pdf_text(line), fontsize=8, color=(0.15, 0.17, 0.20))
                y += 12
            y += 12

    return AnnotatedPdfArtifact(
        data=document.tobytes(garbage=3, deflate=True),
        kind="semantic_report",
        annotated_blocks=0,
        semantic_blocks=semantic,
    )


def _new_report_page(document: fitz.Document) -> fitz.Page:
    page = document.new_page(width=595, height=842)
    page.insert_text((40, 42), "Paperplane evidence review", fontsize=18, color=(0.05, 0.16, 0.32))
    page.insert_text(
        (40, 62),
        "Semantic-only source: coordinates were not invented.",
        fontsize=8,
        color=(0.35, 0.39, 0.45),
    )
    return page


def _content_nodes(root: StructureNode) -> Iterator[StructureNode]:
    for child in root.children:
        if child.type != "page":
            yield child
        yield from _content_nodes(child)


def _plain_excerpt(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split())[:360]


def _pdf_text(value: str) -> str:
    return value.encode("latin-1", errors="replace").decode("latin-1")


__all__ = ["AnnotatedPdfArtifact", "build_annotated_pdf"]
