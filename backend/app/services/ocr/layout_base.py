"""Layout-aware parsing for v0.5.0.

A layout parser is a strict superset of an OCR parser: it returns
not only text and per-page text, but per-region metadata that
downstream stages (evidence tracking, verifier, cross-page entity
resolution) can act on.

The base contract
-----------------

``BaseLayoutProvider.extract_layout(file_path) -> LayoutResult``

Every layout provider MUST populate:

* ``text`` — flat text, page-separated by ``\\n\\n``.
* ``pages`` — list of per-page flat text.
* ``provider`` — provider id.
* ``tokens`` — list of ``LayoutToken`` (text + bbox + page +
  ``region_type``).
* ``regions`` — list of ``LayoutRegion`` (logical grouping:
  paragraph / heading / table / form-field / figure / header /
  footer / signature).
* ``tables`` — list of ``LayoutTable`` (cells + bbox + page +
  region id).
* ``reading_order`` — list of region ids in document order.
* ``page_count`` — number of pages.

Backward compatibility
----------------------

``BaseLayoutProvider`` is *additive*: it does not replace
``BaseOCRProvider``. Existing OCR providers keep their old contract
so v0.4.0 paths stay green. To bridge: ``LayoutResult.from_ocr_result``
maps a v0.4.0 ``OCRResult`` to a layout result with empty regions,
no bbox, no table cells, no reading order. The downstream stages
treat this as "no metadata; degrade gracefully".
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.ocr.base import (
    OCRBlock,
    OCRProviderError,
    OCRResult,
    OCRTable,
)

# ── Region types ─────────────────────────────────────────────────────

# Logical region types emitted by layout parsers. They are a
# superset of what any single engine today produces; providers fill
# in what they can and leave the rest empty.
REGION_TYPES: tuple[str, ...] = (
    "paragraph",
    "heading",
    "title",
    "table",
    "form_field",
    "figure",
    "caption",
    "header",
    "footer",
    "signature",
    "list",
    "other",
)


def normalize_region_type(value: str | None) -> str:
    """Coerce an engine's region label to one of ``REGION_TYPES``."""

    if not value:
        return "other"
    # CamelCase -> snake_case: insert underscore before uppercase letters
    spaced = []
    for i, ch in enumerate(value):
        if ch.isupper() and i > 0 and value[i - 1].islower():
            spaced.append("_")
        spaced.append(ch)
    snake = "".join(spaced)
    lowered = snake.strip().lower().replace(" ", "_").replace("-", "_")
    # Collapse double underscores
    while "__" in lowered:
        lowered = lowered.replace("__", "_")
    for candidate in REGION_TYPES:
        if candidate in lowered:
            return candidate
    return "other"


# ── Structured sub-result types ───────────────────────────────────────


@dataclass(frozen=True)
class LayoutToken:
    """A single text token with spatial and regional metadata.

    ``bbox`` is ``(x0, y0, x1, y1)`` in normalized 0..1 coordinates
    of the page. Normalized coordinates keep the layout stable
    across DPI / render size and make IoU well-defined.
    """

    text: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    region_id: str | None = None
    region_type: str = "other"
    confidence: float | None = None

    def __post_init__(self) -> None:
        # Force region_type to a known set
        object.__setattr__(self, "region_type", normalize_region_type(self.region_type))


@dataclass(frozen=True)
class LayoutRegion:
    """A logical grouping of tokens (paragraph, table, form-field, ...)."""

    region_id: str
    region_type: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    text: str = ""
    confidence: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "region_type", normalize_region_type(self.region_type))


@dataclass(frozen=True)
class LayoutTable:
    """A detected table with cells and structural metadata."""

    table_id: str
    page: int
    cells: list[list[str]]
    bbox: tuple[float, float, float, float] | None = None
    region_id: str | None = None
    confidence: float | None = None
    header_rows: int = 1
    n_rows: int = 0
    n_cols: int = 0

    def __post_init__(self) -> None:
        if self.n_rows == 0 and self.cells:
            object.__setattr__(self, "n_rows", len(self.cells))
        if self.n_cols == 0 and self.cells:
            widths = {len(r) for r in self.cells}
            if len(widths) == 1:
                object.__setattr__(self, "n_cols", next(iter(widths)))


@dataclass(frozen=True)
class LayoutResult:
    """Normalized output of a layout-aware parser.

    All four ``text``/``pages``/``tokens``/``regions`` collections
    are kept consistent. ``tokens`` is the fine-grained view (one
    element per word/line) and ``regions`` is the coarse view
    (paragraph, table, ...). ``reading_order`` lists region ids in
    document order.
    """

    text: str
    pages: list[str]
    provider: str
    page_count: int
    tokens: list[LayoutToken] = field(default_factory=list)
    regions: list[LayoutRegion] = field(default_factory=list)
    tables: list[LayoutTable] = field(default_factory=list)
    reading_order: list[str] = field(default_factory=list)
    confidence: float | None = None
    raw: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        # If no pages, build one from text
        normalized_pages = list(self.pages)
        if not normalized_pages:
            normalized_pages = [self.text] if self.text else [""]
        object.__setattr__(self, "pages", normalized_pages)

        if self.page_count == 0:
            object.__setattr__(self, "page_count", len(normalized_pages))

        # Make sure the text field is consistent with the page list
        if not self.text:
            object.__setattr__(self, "text", "\n\n".join(normalized_pages))

        # raw/metadata compatibility alias
        if self.raw is None and self.metadata is not None:
            object.__setattr__(self, "raw", self.metadata)
        if self.metadata is None and self.raw is not None:
            object.__setattr__(self, "metadata", self.raw)

    # ── Convenience views ────────────────────────────────────────────

    def tokens_on_page(self, page: int) -> list[LayoutToken]:
        return [t for t in self.tokens if t.page == page]

    def regions_on_page(self, page: int) -> list[LayoutRegion]:
        return [r for r in self.regions if r.page == page]

    def tables_on_page(self, page: int) -> list[LayoutTable]:
        return [t for t in self.tables if t.page == page]

    def region_by_id(self, region_id: str) -> LayoutRegion | None:
        for r in self.regions:
            if r.region_id == region_id:
                return r
        return None

    def to_ocr_result(self) -> OCRResult:
        """Down-cast to a v0.4.0 ``OCRResult`` for legacy paths."""

        blocks = [
            OCRBlock(
                text=t.text,
                bbox=t.bbox,
                confidence=t.confidence,
                label=t.region_type,
            )
            for t in self.tokens
        ]
        tables = [
            OCRTable(
                cells=tbl.cells,
                bbox=tbl.bbox,
                confidence=tbl.confidence,
                page_index=tbl.page,
            )
            for tbl in self.tables
        ]
        return OCRResult(
            text=self.text,
            pages=self.pages,
            provider=self.provider,
            blocks=blocks,
            tables=tables,
            confidence=self.confidence,
            raw=self.raw,
            metadata=self.metadata,
        )

    @classmethod
    def from_ocr_result(
        cls,
        ocr: OCRResult,
        *,
        provider_override: str | None = None,
    ) -> LayoutResult:
        """Bridge a v0.4.0 ``OCRResult`` to a layout result.

        No spatial metadata, no regions, no reading order; just the
        text + per-page text. Downstream stages degrade gracefully
        when ``tokens``/``regions`` are empty.
        """

        tokens: list[LayoutToken] = []
        for page_index, page in enumerate(ocr.page_results or []):
            for block in page.blocks:
                tokens.append(
                    LayoutToken(
                        text=block.text,
                        page=page_index,
                        bbox=block.bbox,
                        region_id=None,
                        region_type=block.label or "other",
                        confidence=block.confidence,
                    )
                )
        # If the OCR result had no per-page blocks, seed one token
        # per page so callers can still resolve page numbers.
        if not tokens and ocr.pages:
            for idx, page_text in enumerate(ocr.pages):
                tokens.append(LayoutToken(text=page_text, page=idx))
        return cls(
            text=ocr.text,
            pages=list(ocr.pages),
            provider=provider_override or ocr.provider,
            page_count=len(ocr.pages),
            tokens=tokens,
            regions=[],
            tables=[],
            reading_order=[],
            confidence=ocr.confidence,
            raw=ocr.raw,
            metadata=ocr.metadata,
        )


# ── Provider interface ───────────────────────────────────────────────


class BaseLayoutProvider(ABC):
    """Interface for layout-aware parsers.

    Implementations are typically *also* an ``BaseOCRProvider``
    (Docling is). The layout extraction is a richer entry point
    that the v0.5.0 graph calls when ``enable_layout_parsing`` is
    True. Otherwise the v0.4.0 OCR path is used and the result is
    bridged via ``LayoutResult.from_ocr_result``.
    """

    feature_flag_name: str | None = None
    is_user_selectable: bool = True
    supported_file_types: frozenset[str] | None = None

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier (e.g. 'docling-layout')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    async def extract_layout(self, file_path: Path) -> LayoutResult:
        """Run layout-aware parsing and return a ``LayoutResult``."""

    def is_available(self) -> bool:
        """Check whether this provider's dependencies are installed."""

        return True

    def supports_file_type(self, file_type: str | None) -> bool:
        """Return whether this provider can safely handle the given file type."""

        return (
            file_type is None
            or self.supported_file_types is None
            or file_type in self.supported_file_types
        )


# ── Errors ───────────────────────────────────────────────────────────


class LayoutProviderError(OCRProviderError):
    """Raised when a layout provider encounters an error."""


class LayoutProviderUnavailableError(LayoutProviderError):
    """Raised when a specifically-requested layout engine is not available."""
