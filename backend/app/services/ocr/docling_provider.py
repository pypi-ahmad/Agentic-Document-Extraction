"""Docling-backed local OCR/parser provider.

Docling (https://github.com/DS4SD/docling) is an IBM-developed
document parser that converts PDF, DOCX, PPTX, XLSX, images, and
HTML into structured Markdown or JSON. It runs locally, is GPU-
accelerated when available, and includes its own layout-analysis and
table-structure models. Compared to PaddleOCR (text only) and
GLM-OCR (vision), Docling is the best choice when the document has
complex tables, multi-column layouts, or a mix of figures and text.

Install
-------

- ``pip install docling`` (or the ``ade[docling]`` extra).
- The first run downloads the model weights (~1.5 GB total) to
  ``~/.cache/docling/``.

Trade-offs
----------

- Heavier than PaddleOCR / GLM-OCR (model weights, longer cold start).
- Slowest of the three on small images (overkill for a single
  receipt). Fastest of the three on a 50-page financial report.
- Outputs Markdown by default; we flatten that to plain text so
  the rest of the pipeline (LLM extractor) sees a single string.
- When ``is_available()`` is False, the provider reports itself as
  unavailable and Auto routing falls through to the next engine.

Requires ``ENABLE_DOCLING=true`` in ``.env`` to be visible in the
UI; otherwise it is still importable but is filtered out of
``list_ocr_provider_statuses()``.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from app.models.enums import ParserEngine
from app.services.ocr.base import (
    BaseOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProviderError,
    OCRResult,
)


class DoclingProvider(BaseOCRProvider):
    feature_flag_name = "enable_docling"
    # Docling handles a broader set than the other parsers; PDFs,
    # DOCX, PPTX, XLSX, images, HTML. We expose the common ones.
    supported_file_types = frozenset({"pdf", "docx", "pptx", "xlsx", "png", "jpeg", "tiff", "html"})

    @property
    def provider_id(self) -> str:
        return ParserEngine.DOCLING.value

    @property
    def display_name(self) -> str:
        return "Docling (IBM, local structured parser)"

    async def extract_text(self, file_path: Path) -> OCRResult:
        if not self.is_available():
            raise OCRProviderError(
                self.provider_id,
                "docling is not installed. Run: pip install docling",
            )
        try:
            from docling.document_converter import DocumentConverter  # type: ignore[import-untyped]
        except Exception as exc:  # pragma: no cover — defensive
            raise OCRProviderError(self.provider_id, str(exc)) from exc

        converter = DocumentConverter()
        result = converter.convert(str(file_path))

        # Docling returns a DoclingDocument; export to markdown for
        # the page text, and use the per-page text when available.
        try:
            markdown = result.document.export_to_markdown()
        except Exception:  # pragma: no cover — defensive
            markdown = getattr(result.document, "text", "") or ""

        # Docling exposes per-page content in ``document.pages``;
        # when that's available, build per-page text; otherwise
        # fall back to a single page containing the full markdown.
        pages: list[str] = []
        page_results: list[OCRPageResult] = []
        try:
            doc_pages = list(getattr(result.document, "pages", []) or [])
        except Exception:  # pragma: no cover — defensive
            doc_pages = []
        if doc_pages:
            for idx, page in enumerate(doc_pages):
                page_text = getattr(page, "text", "") or ""
                pages.append(page_text)
                page_results.append(
                    OCRPageResult(
                        page_index=idx,
                        text=page_text,
                        blocks=[OCRBlock(text=page_text, bbox=None, confidence=None)],
                    )
                )
        else:
            pages.append(markdown)
            page_results.append(
                OCRPageResult(
                    page_index=0,
                    text=markdown,
                    blocks=[OCRBlock(text=markdown, bbox=None, confidence=None)],
                )
            )

        return OCRResult(
            text="\n\n".join(pages),
            pages=pages,
            provider=self.provider_id,
            page_results=page_results,
            confidence=None,  # Docling does not expose per-block confidences.
            raw={
                "engine": "docling",
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
