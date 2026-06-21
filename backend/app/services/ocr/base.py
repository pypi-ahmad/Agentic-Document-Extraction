"""Abstract base classes and normalized result types for OCR providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── Structured sub-result types ──────────────────────────────────────


@dataclass(frozen=True)
class OCRBlock:
    """A detected text region/block within a page."""

    text: str
    bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)
    confidence: float | None = None
    label: str = ""  # e.g. "paragraph", "title", "caption"


@dataclass(frozen=True)
class OCRTable:
    """A detected table within a page."""

    cells: list[list[str]]  # 2-D grid: rows x columns
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    page_index: int = 0


@dataclass(frozen=True)
class OCRPageResult:
    """Per-page parsing output."""

    page_index: int
    text: str
    blocks: list[OCRBlock] = field(default_factory=list)
    tables: list[OCRTable] = field(default_factory=list)
    confidence: float | None = None


@dataclass(frozen=True)
class OCRResult:
    """Normalized result from any OCR / parser provider.

    Every provider must populate at least ``text``, ``pages``, and
    ``provider``. Richer fields (``page_results``, ``blocks``,
    ``tables``, ``confidence``, ``raw``) are filled when the underlying
    engine supports them.

    ``metadata`` is kept as a compatibility alias for older integrations
    that constructed ``OCRResult(..., metadata=...)`` before the result
    schema was normalized around ``raw``.
    """

    text: str
    pages: list[str]
    provider: str
    page_results: list[OCRPageResult] = field(default_factory=list)
    blocks: list[OCRBlock] = field(default_factory=list)
    tables: list[OCRTable] = field(default_factory=list)
    confidence: float | None = None
    raw: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        normalized_pages = list(self.pages)
        normalized_page_results = list(self.page_results)

        if not normalized_pages and normalized_page_results:
            normalized_pages = [page.text for page in normalized_page_results]

        if not normalized_page_results and normalized_pages:
            normalized_page_results = [
                OCRPageResult(page_index=index, text=page_text)
                for index, page_text in enumerate(normalized_pages)
            ]

        normalized_blocks = list(self.blocks)
        if not normalized_blocks and normalized_page_results:
            normalized_blocks = [block for page in normalized_page_results for block in page.blocks]

        normalized_tables = list(self.tables)
        if not normalized_tables and normalized_page_results:
            normalized_tables = [table for page in normalized_page_results for table in page.tables]

        normalized_raw = self.raw if self.raw is not None else self.metadata
        normalized_metadata = self.metadata if self.metadata is not None else normalized_raw
        normalized_text = self.text or "\n\n".join(normalized_pages)

        object.__setattr__(self, "text", normalized_text)
        object.__setattr__(self, "pages", normalized_pages)
        object.__setattr__(self, "page_results", normalized_page_results)
        object.__setattr__(self, "blocks", normalized_blocks)
        object.__setattr__(self, "tables", normalized_tables)
        object.__setattr__(self, "raw", normalized_raw)
        object.__setattr__(self, "metadata", normalized_metadata)

    @property
    def regions(self) -> list[OCRBlock]:
        """Compatibility alias for callers that use 'regions' wording."""

        return self.blocks


# ── Provider interface ───────────────────────────────────────────────


class BaseOCRProvider(ABC):
    """Interface every OCR provider must implement."""

    feature_flag_name: str | None = None
    is_user_selectable: bool = True
    supported_file_types: frozenset[str] | None = None

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider (e.g. 'paddleocr')."""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name shown in the UI."""

    @abstractmethod
    async def extract_text(self, file_path: Path) -> OCRResult:
        """Extract text from a document file.

        Args:
            file_path: Path to the uploaded document (PDF or image).

        Returns:
            OCRResult with extracted text.

        Raises:
            OCRProviderError: If extraction fails.
        """

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


class OCRProviderError(Exception):
    """Raised when an OCR provider encounters an error."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class OCRProviderUnavailableError(OCRProviderError):
    """Raised when a specifically-requested engine is not available."""
