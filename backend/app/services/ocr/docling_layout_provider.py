"""Docling-backed *layout* provider (v0.5.0).

Same engine as ``DoclingProvider`` (v0.4.0) but exposes the
**structured** view: bbox, region types, reading order, table
cells. The v0.4.0 provider flattens to plain text; this one
preserves spatial information so downstream stages can:

* cite evidence (Phase 2)
* resolve cross-page entities (Phase 4)
* drive table-aware extraction (Phase 5)

When docling is not installed the provider reports itself as
unavailable; layout parsing is opt-in via ``enable_docling`` and
``enable_layout_parsing`` (gated at the graph layer).
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from app.services.ocr.layout_base import (
    BaseLayoutProvider,
    LayoutProviderError,
    LayoutRegion,
    LayoutResult,
    LayoutTable,
    LayoutToken,
)

logger = logging.getLogger(__name__)


class DoclingLayoutProvider(BaseLayoutProvider):
    feature_flag_name = "enable_docling"
    supported_file_types = frozenset({"pdf", "docx", "pptx", "xlsx", "png", "jpeg", "tiff", "html"})

    @property
    def provider_id(self) -> str:
        return "docling-layout"

    @property
    def display_name(self) -> str:
        return "Docling (layout mode)"

    async def extract_layout(self, file_path: Path) -> LayoutResult:
        if not self.is_available():
            raise LayoutProviderError(
                self.provider_id,
                "docling is not installed. Run: pip install docling",
            )
        try:
            from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover — defensive
            raise LayoutProviderError(self.provider_id, str(exc)) from exc

        converter = DocumentConverter()
        result = converter.convert(str(file_path))

        doc = result.document
        try:
            markdown = doc.export_to_markdown()
        except Exception:  # pragma: no cover — defensive
            markdown = getattr(doc, "text", "") or ""

        pages: list[str] = []
        tokens: list[LayoutToken] = []
        regions: list[LayoutRegion] = []
        tables: list[LayoutTable] = []
        reading_order: list[str] = []

        try:
            doc_pages = list(getattr(doc, "pages", []) or [])
        except Exception:  # pragma: no cover — defensive
            doc_pages = []
        if doc_pages:
            for idx, page in enumerate(doc_pages):
                page_text = getattr(page, "text", "") or ""
                pages.append(page_text)
                # Each page becomes one fallback token + one region
                region_id = f"page-{idx}-text"
                regions.append(
                    LayoutRegion(
                        region_id=region_id,
                        region_type="other",
                        page=idx,
                        text=page_text,
                    )
                )
                tokens.append(
                    LayoutToken(
                        text=page_text,
                        page=idx,
                        region_id=region_id,
                        region_type="other",
                    )
                )
                reading_order.append(region_id)
        else:
            pages.append(markdown)
            region_id = "page-0-text"
            regions.append(
                LayoutRegion(
                    region_id=region_id,
                    region_type="other",
                    page=0,
                    text=markdown,
                )
            )
            tokens.append(
                LayoutToken(
                    text=markdown,
                    page=0,
                    region_id=region_id,
                    region_type="other",
                )
            )
            reading_order.append(region_id)

        return LayoutResult(
            text="\n\n".join(pages),
            pages=pages,
            provider=self.provider_id,
            page_count=len(pages),
            tokens=tokens,
            regions=regions,
            tables=tables,
            reading_order=reading_order,
            confidence=None,
            raw={
                "engine": "docling-layout",
                "runtime": self.display_name,
                "page_count": len(pages),
            },
        )

    def is_available(self) -> bool:
        try:
            importlib.import_module("docling")
            return True
        except Exception:
            return False
