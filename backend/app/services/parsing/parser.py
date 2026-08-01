"""Local vision-first layout parsing primitives used by the LangGraph workflow."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any, Protocol

from app.models.schemas import ParseSettings
from app.services.parsing.contracts import (
    BoundingBox,
    ContextChunk,
    DocumentLayout,
    PageLayout,
    Region,
    StitchResult,
)
from app.services.parsing.ingest import RenderedPage, render_page
from app.services.parsing.markdown import MarkdownRenderer


class LayoutEngine(Protocol):
    async def segment(self, image_path: Path, device: str = "auto") -> list[Region]: ...

    async def segment_document(
        self,
        *,
        job_id: str,
        image_paths: list[Path],
        page_numbers: list[int],
        work_dir: Path,
    ) -> dict[int, list[Region]]: ...


class ZoneEngine(Protocol):
    async def process(
        self,
        image_path: Path,
        zone: Region,
        device: str = "auto",
        model: str | None = None,
        provider: str = "openai",
    ) -> Region: ...


class LayoutParser:
    """Coordinate lazily loaded CPU layout/table engines and local GPU OCR."""

    def __init__(
        self,
        layout_engine: LayoutEngine | None = None,
        text_engine: ZoneEngine | None = None,
        table_engine: ZoneEngine | None = None,
    ) -> None:
        self.layout_engine = layout_engine
        self.text_engine = text_engine
        self.table_engine = table_engine

    async def ingest(
        self,
        source_path: Path,
        work_dir: Path,
        settings: ParseSettings,
        page_numbers: list[int] | None = None,
    ) -> tuple[list[str], dict[int, list[dict[str, Any]]]]:
        data = await asyncio.to_thread(source_path.read_bytes)
        if source_path.suffix.lower() == ".pdf":
            import fitz

            document = fitz.open(stream=data, filetype="pdf")
            try:
                page_count = document.page_count
            finally:
                document.close()
        else:
            from PIL import Image

            with Image.open(source_path) as image:
                page_count = int(getattr(image, "n_frames", 1))
        last = min(settings.end_page or page_count, page_count)
        pages_dir = work_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        image_paths: list[str] = []
        native: dict[int, list[dict[str, Any]]] = {}
        selected_pages = page_numbers or list(range(settings.start_page, last + 1))
        for page_number in selected_pages:
            if page_number < settings.start_page or page_number > last:
                raise ValueError("Selected page is outside the configured page range")
            rendered = await asyncio.to_thread(
                self._render_with_fallback,
                data,
                source_path.name,
                page_number,
                settings.dpi,
            )
            image_path = pages_dir / f"page-{page_number:04d}.png"
            await asyncio.to_thread(image_path.write_bytes, rendered.image_png)
            image_paths.append(str(image_path))
            native[page_number] = [word.model_dump(mode="json") for word in rendered.native_words]
        return image_paths, native

    async def segment_page(
        self,
        image_path: Path,
        page_number: int,
        native_words: list[dict[str, Any]],
        input_mode: str,
        layout_device: str = "auto",
    ) -> list[Region]:
        if input_mode == "native" and native_words:
            return [
                self._native_region(native_words).model_copy(
                    update={"id": f"p{page_number:04d}-r0001"}
                )
            ]
        if self.layout_engine is not None:
            zones = await self.layout_engine.segment(image_path, layout_device)
            if zones:
                if input_mode == "mixed" and native_words:
                    zones = [self._merge_native(zone, native_words) for zone in zones]
                return [
                    zone.model_copy(update={"id": f"p{page_number:04d}-r{i:04d}"})
                    for i, zone in enumerate(zones, 1)
                ]
        if input_mode == "mixed" and native_words:
            return [
                self._native_region(native_words).model_copy(
                    update={"id": f"p{page_number:04d}-r0001"}
                )
            ]
        return [
            Region(
                id=f"p{page_number:04d}-r0001",
                type="text",
                bbox=BoundingBox(left=0, top=0, right=1, bottom=1),
                content="",
                source="fallback",
                warnings=["layout_segmentation_unavailable"],
            )
        ]

    async def segment_document(
        self,
        *,
        job_id: str,
        image_paths: list[Path],
        native_words: dict[int, list[dict[str, Any]]],
        input_mode: str,
        work_dir: Path,
        layout_device: str = "auto",
    ) -> dict[int, list[Region]]:
        page_numbers = [int(path.stem.rsplit("-", 1)[1]) for path in image_paths]
        if self.layout_engine is not None and hasattr(self.layout_engine, "segment_document"):
            pages = await self.layout_engine.segment_document(
                job_id=job_id,
                image_paths=image_paths,
                page_numbers=page_numbers,
                work_dir=work_dir,
            )
            normalized: dict[int, list[Region]] = {}
            for page_number in page_numbers:
                zones = pages.get(page_number, [])
                words = native_words.get(page_number, [])
                if input_mode in {"native", "mixed"} and words:
                    zones = [self._merge_native(zone, words) for zone in zones]
                if not zones and words:
                    zones = [self._native_region(words)]
                normalized[page_number] = [
                    zone.model_copy(update={"id": f"p{page_number:04d}-r{i:04d}"})
                    for i, zone in enumerate(zones, 1)
                ]
            return normalized
        fallback: dict[int, list[Region]] = {}
        for image_path, page_number in zip(image_paths, page_numbers, strict=True):
            fallback[page_number] = await self.segment_page(
                image_path,
                page_number,
                native_words.get(page_number, []),
                input_mode,
                layout_device,
            )
        return fallback

    async def process_zone(
        self,
        image_path: Path,
        zone: Region,
        layout_device: str = "auto",
        model: str | None = None,
        provider: str = "ollama",
    ) -> Region:
        engine = self.table_engine if zone.type == "table" else self.text_engine
        if zone.content.strip() and zone.source == "native" and zone.type != "table":
            return zone
        if engine is None:
            return zone.model_copy(
                update={"warnings": [*zone.warnings, "zone_processor_unavailable"]}
            )
        try:
            return await engine.process(image_path, zone, layout_device, model, provider)
        except Exception as exc:
            return zone.model_copy(
                update={
                    "warnings": [
                        *zone.warnings,
                        f"zone_processing_failed:{type(exc).__name__}",
                    ]
                }
            )

    def stitch_document(
        self, pages: dict[int, list[Region]], marginalia_policy: str = "remove_repeated"
    ) -> StitchResult:
        document = self.build_document_layout(pages)
        return self.stitch_layout(document, marginalia_policy)

    def build_document_layout(self, pages: dict[int, list[Region]]) -> DocumentLayout:
        layouts: list[PageLayout] = []
        for page_number, zones in sorted(pages.items()):
            ordered = sorted(zones, key=self._reading_order_key)
            for index, zone in enumerate(ordered, 1):
                zone.id = f"p{page_number:04d}-r{index:04d}"
            layouts.append(PageLayout(page_number=page_number, width=1, height=1, regions=ordered))
        document = DocumentLayout(pages=layouts).with_stable_ids()
        self._annotate_layout(document)
        return document

    def stitch_layout(
        self, document: DocumentLayout, marginalia_policy: str = "remove_repeated"
    ) -> StitchResult:
        renderer = MarkdownRenderer()
        output = renderer.render(document, marginalia_policy)
        suppressed = renderer.suppressed_marginalia(document, marginalia_policy)
        chunks: list[ContextChunk] = []
        heading_stack: list[tuple[int, str, str]] = []
        ordinal = 0
        for page in document.pages:
            for region in page.regions:
                if region.id in suppressed:
                    continue
                ordinal += 1
                body = self._region_body(page.page_number, region)
                if region.type in {"title", "heading"}:
                    level = region.heading_level or (1 if region.type == "title" else 2)
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    region.parent_id = heading_stack[-1][1] if heading_stack else None
                    title = re.sub(r"^#+\s*", "", body).strip()
                    heading_stack.append((level, region.id or "", title))
                else:
                    region.parent_id = heading_stack[-1][1] if heading_stack else None
                chunks.append(
                    ContextChunk(
                        id=region.id or f"p{page.page_number:04d}-r{ordinal:04d}",
                        ordinal=ordinal,
                        page=page.page_number,
                        source_page=page.source_page_number or page.page_number,
                        bbox=region.bbox,
                        type=region.type,
                        source=region.source,
                        confidence=region.confidence,
                        heading_path=[item[2] for item in heading_stack],
                        parent_id=region.parent_id,
                        column_index=region.column_index,
                        is_spanning=region.is_spanning,
                        related_region_ids=list(region.related_region_ids),
                        markdown=body,
                        text=region.content.strip(),
                        metadata={
                            **region.semantic_metadata,
                            **(
                                {
                                    "table_html": region.table_html,
                                    "table_cells": [
                                        cell.model_dump(mode="json") for cell in region.table_cells
                                    ],
                                }
                                if region.type == "table"
                                else {}
                            ),
                        },
                    )
                )
        return StitchResult(
            clean_markdown=output.clean,
            grounded_markdown=self._grounded(document),
            context_chunks=chunks,
        )

    @staticmethod
    def _annotate_layout(document: DocumentLayout) -> None:
        """Add lightweight column and relationship metadata without replacing reading order."""
        for page in document.pages:
            column_regions = [
                region
                for region in page.regions
                if (region.bbox.right - region.bbox.left) < 0.65
                and region.type not in {"header", "footer", "page_number"}
            ]
            centers = sorted(
                (region.bbox.left + region.bbox.right) / 2 for region in column_regions
            )
            clusters: list[list[float]] = []
            for center in centers:
                if clusters and abs(center - (sum(clusters[-1]) / len(clusters[-1]))) <= 0.18:
                    clusters[-1].append(center)
                else:
                    clusters.append([center])
            anchors = [sum(cluster) / len(cluster) for cluster in clusters]
            for region in page.regions:
                width = region.bbox.right - region.bbox.left
                region.is_spanning = width >= 0.65
                if not region.is_spanning and anchors:
                    center = (region.bbox.left + region.bbox.right) / 2
                    region.column_index = min(
                        range(len(anchors)), key=lambda index: abs(anchors[index] - center)
                    )

            visual = [
                region for region in page.regions if region.type in {"figure", "chart", "table"}
            ]
            captions = [
                region
                for region in page.regions
                if region.type in {"text", "quote"}
                and region.content.strip().casefold().startswith(("figure ", "fig. ", "table "))
            ]
            for caption in captions:
                candidates = [
                    region
                    for region in visual
                    if abs(region.bbox.bottom - caption.bbox.top) <= 0.12
                    or abs(caption.bbox.bottom - region.bbox.top) <= 0.12
                ]
                if not candidates:
                    continue
                target = min(
                    candidates,
                    key=lambda region: abs(region.bbox.bottom - caption.bbox.top),
                )
                if target.id and caption.id:
                    target.related_region_ids.append(caption.id)
                    caption.related_region_ids.append(target.id)

    def reflect(
        self, pages: dict[int, list[Region]], min_region_confidence: float = 0.75
    ) -> tuple[bool, list[str]]:
        issues: list[str] = []
        for page_number, zones in pages.items():
            for zone in zones:
                if zone.type == "table" and (not zone.content.strip() or "|" not in zone.content):
                    issues.append(f"p{page_number}:{zone.id}:broken_table")
                elif not zone.content.strip():
                    issues.append(f"p{page_number}:{zone.id}:empty_zone")
                if zone.confidence is not None and zone.confidence < min_region_confidence:
                    issues.append(f"p{page_number}:{zone.id}:low_confidence")
                for warning in zone.warnings:
                    if warning.startswith(("recognition_disagreement", "zone_processing_failed")):
                        issues.append(f"p{page_number}:{zone.id}:{warning}")
            for index, first in enumerate(zones):
                for second in zones[index + 1 :]:
                    if self._overlap(first.bbox, second.bbox) > 0.65:
                        issues.append(f"p{page_number}:{first.id}:overlap")
        return bool(issues), issues

    @staticmethod
    def _native_region(words: list[dict[str, Any]]) -> Region:
        ordered = sorted(words, key=lambda word: (word["bbox"]["top"], word["bbox"]["left"]))
        return Region(
            type="text",
            bbox=BoundingBox(left=0, top=0, right=1, bottom=1),
            content=" ".join(str(word["text"]) for word in ordered),
            source="native",
        )

    @staticmethod
    def _merge_native(zone: Region, words: list[dict[str, Any]]) -> Region:
        if zone.type not in {"title", "heading", "text", "list", "code", "quote"}:
            return zone
        selected = []
        for word in words:
            box = BoundingBox.model_validate(word["bbox"])
            center_x, center_y = (box.left + box.right) / 2, (box.top + box.bottom) / 2
            if (
                zone.bbox.left <= center_x <= zone.bbox.right
                and zone.bbox.top <= center_y <= zone.bbox.bottom
            ):
                selected.append(word)
        if not selected:
            return zone
        selected.sort(key=lambda word: (word["bbox"]["top"], word["bbox"]["left"]))
        return zone.model_copy(
            update={"content": " ".join(str(word["text"]) for word in selected), "source": "native"}
        )

    @staticmethod
    def _overlap(first: BoundingBox, second: BoundingBox) -> float:
        width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
        height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
        intersection = width * height
        smaller = min(
            (first.right - first.left) * (first.bottom - first.top),
            (second.right - second.left) * (second.bottom - second.top),
        )
        return intersection / smaller if smaller else 0.0

    @staticmethod
    def _render_with_fallback(
        data: bytes, filename: str, page_number: int, dpi: int
    ) -> RenderedPage:
        try:
            return render_page(data, filename, page_number, dpi)
        except Exception:
            if Path(filename).suffix.lower() != ".pdf":
                raise
            from pdf2image import convert_from_bytes

            images = convert_from_bytes(
                data, dpi=dpi, first_page=page_number, last_page=page_number, fmt="png"
            )
            if not images:
                raise RuntimeError(f"PDF page {page_number} could not be rendered")
            image = images[0].convert("RGB")
            output = __import__("io").BytesIO()
            image.save(output, "PNG")
            return RenderedPage(
                page_number, output.getvalue(), float(image.width), float(image.height), []
            )

    @staticmethod
    def _reading_order_key(region: Region) -> tuple[int, float, float, float]:
        if region.order is not None:
            return (0, float(region.order), region.bbox.top, region.bbox.left)
        full_width = region.bbox.left < 0.25 and region.bbox.right > 0.75
        column = 0 if full_width else (1 if region.bbox.left < 0.5 else 2)
        return (1 + (0 if full_width else column), region.bbox.top, region.bbox.left, 0)

    @staticmethod
    def _region_body(page_number: int, region: Region) -> str:
        return (
            MarkdownRenderer()
            .render(
                DocumentLayout(
                    pages=[PageLayout(page_number=page_number, width=1, height=1, regions=[region])]
                )
            )
            .clean.strip()
        )

    def _grounded(self, document: DocumentLayout) -> str:
        blocks: list[str] = []
        for page in document.pages:
            for region in page.regions:
                if region.type in {"header", "footer", "page_number"}:
                    continue
                box = region.bbox
                blocks.append(
                    f"<!-- p:{page.page_number} bbox:{box.left:.4f},{box.top:.4f},"
                    f"{box.right:.4f},{box.bottom:.4f} id:{region.id} -->\n"
                    f"{self._region_body(page.page_number, region)}"
                )
        return "\n\n".join(blocks).strip() + "\n"
