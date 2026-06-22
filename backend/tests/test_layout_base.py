"""Tests for the v0.5.0 layout-aware parsing module."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ocr.base import OCRBlock, OCRPageResult, OCRResult, OCRTable
from app.services.ocr.layout_base import (
    BaseLayoutProvider,
    LayoutProviderError,
    LayoutRegion,
    LayoutResult,
    LayoutToken,
    normalize_region_type,
)
from app.services.ocr.layout_base import (
    LayoutTable as LayoutTableNew,
)
from app.services.ocr.layout_registry import (
    _PROVIDERS,
    LAYOUT_AUTO_PRIORITY,
    LayoutProviderStatus,
    _ensure_registered,
    get_layout_provider,
    list_layout_provider_statuses,
    register_layout_provider,
    reset_layout_registry,
)

# ── normalize_region_type ────────────────────────────────────────────


def test_normalize_region_type_handles_known_labels() -> None:
    assert normalize_region_type("Paragraph") == "paragraph"
    assert normalize_region_type("TABLE") == "table"
    assert normalize_region_type("form field") == "form_field"
    assert normalize_region_type("page-header") == "header"


def test_normalize_region_type_falls_back_to_other() -> None:
    assert normalize_region_type(None) == "other"
    assert normalize_region_type("") == "other"
    assert normalize_region_type("gibberish") == "other"


# ── LayoutToken / LayoutRegion / LayoutTable ────────────────────────


def test_layout_token_normalizes_region_type_on_init() -> None:
    token = LayoutToken(text="hi", page=0, region_type="FormField")
    assert token.region_type == "form_field"


def test_layout_region_normalizes_region_type_on_init() -> None:
    region = LayoutRegion(region_id="r1", region_type="Title", page=0, text="Hello")
    assert region.region_type == "title"


def test_layout_table_infers_n_rows_and_n_cols() -> None:
    cells = [["A", "B", "C"], ["1", "2", "3"]]
    table = LayoutTableNew(table_id="t1", page=0, cells=cells)
    assert table.n_rows == 2
    assert table.n_cols == 3


def test_layout_table_handles_irregular_cells() -> None:
    cells = [["A", "B", "C"], ["1", "2"]]  # ragged
    table = LayoutTableNew(table_id="t1", page=0, cells=cells)
    assert table.n_rows == 2
    assert table.n_cols == 0  # ragged → unknown


# ── LayoutResult ─────────────────────────────────────────────────────


def _sample_layout() -> LayoutResult:
    tokens = [
        LayoutToken(text="Acme", page=0, bbox=(0.1, 0.1, 0.3, 0.12), region_id="r1"),
        LayoutToken(text="2026-01-15", page=0, bbox=(0.1, 0.2, 0.3, 0.22), region_id="r2"),
        LayoutToken(text="$1,234.50", page=0, bbox=(0.1, 0.3, 0.3, 0.32), region_id="r3"),
    ]
    regions = [
        LayoutRegion(region_id="r1", region_type="other", page=0, text="Acme"),
        LayoutRegion(region_id="r2", region_type="other", page=0, text="2026-01-15"),
        LayoutRegion(region_id="r3", region_type="other", page=0, text="$1,234.50"),
    ]
    tables = [
        LayoutTableNew(
            table_id="t1",
            page=0,
            cells=[["A", "B"], ["1", "2"]],
            region_id="r3",
        )
    ]
    return LayoutResult(
        text="Acme\n2026-01-15\n$1,234.50",
        pages=["Acme\n2026-01-15\n$1,234.50"],
        provider="docling-layout",
        page_count=1,
        tokens=tokens,
        regions=regions,
        tables=tables,
        reading_order=["r1", "r2", "r3"],
    )


def test_layout_result_views() -> None:
    layout = _sample_layout()
    assert len(layout.tokens_on_page(0)) == 3
    assert len(layout.regions_on_page(0)) == 3
    assert len(layout.tables_on_page(0)) == 1
    assert layout.region_by_id("r2") is not None
    assert layout.region_by_id("missing") is None


def test_layout_result_page_count_inferred() -> None:
    layout = LayoutResult(text="", pages=["page1", "page2"], provider="x", page_count=0)
    assert layout.page_count == 2


def test_layout_result_text_inferred_from_pages() -> None:
    layout = LayoutResult(text="", pages=["a", "b"], provider="x", page_count=2)
    assert layout.text == "a\n\nb"


def test_layout_result_raw_metadata_alias() -> None:
    layout = LayoutResult(text="x", pages=["x"], provider="p", page_count=1, raw={"k": 1})
    assert layout.metadata == {"k": 1}
    layout2 = LayoutResult(text="x", pages=["x"], provider="p", page_count=1, metadata={"k": 2})
    assert layout2.raw == {"k": 2}


def test_layout_result_to_ocr_result_preserves_text() -> None:
    layout = _sample_layout()
    ocr = layout.to_ocr_result()
    assert ocr.text == layout.text
    assert ocr.provider == "docling-layout"
    assert len(ocr.blocks) == 3
    assert len(ocr.tables) == 1


def test_layout_result_from_ocr_result_empty_tokens() -> None:
    ocr = OCRResult(text="hello", pages=["hello"], provider="pymupdf")
    layout = LayoutResult.from_ocr_result(ocr)
    assert layout.text == "hello"
    assert layout.page_count == 1
    # Empty blocks → one fallback token per page so callers can still resolve page
    assert len(layout.tokens) == 1
    assert layout.tokens[0].page == 0


def test_layout_result_from_ocr_result_with_blocks() -> None:
    ocr = OCRResult(
        text="page1\n\npage2",
        pages=["page1", "page2"],
        provider="pymupdf",
        page_results=[
            OCRPageResult(
                page_index=0,
                text="page1",
                blocks=[OCRBlock(text="page1", bbox=(0, 0, 1, 0.1), label="paragraph")],
            ),
            OCRPageResult(
                page_index=1,
                text="page2",
                blocks=[OCRBlock(text="page2", bbox=(0, 0, 1, 0.1), label="title")],
            ),
        ],
    )
    layout = LayoutResult.from_ocr_result(ocr)
    assert len(layout.tokens) == 2
    assert layout.tokens[0].page == 0
    assert layout.tokens[0].region_type == "paragraph"
    assert layout.tokens[1].region_type == "title"
    assert layout.page_count == 2


def test_layout_result_from_ocr_result_with_tables() -> None:
    ocr = OCRResult(
        text="t",
        pages=["t"],
        provider="p",
        tables=[OCRTable(cells=[["a", "b"]], page_index=0)],
    )
    layout = LayoutResult.from_ocr_result(ocr)
    assert layout.provider == "p"


def test_layout_result_from_ocr_result_provider_override() -> None:
    ocr = OCRResult(text="x", pages=["x"], provider="pymupdf")
    layout = LayoutResult.from_ocr_result(ocr, provider_override="docling-layout")
    assert layout.provider == "docling-layout"


# ── BaseLayoutProvider interface ────────────────────────────────────


class _StubProvider(BaseLayoutProvider):
    feature_flag_name = None
    supported_file_types = frozenset({"pdf"})

    @property
    def provider_id(self) -> str:
        return "stub"

    @property
    def display_name(self) -> str:
        return "Stub"

    async def extract_layout(self, file_path: Path) -> LayoutResult:
        return LayoutResult(text="x", pages=["x"], provider=self.provider_id, page_count=1)


def test_stub_provider_supports_file_type() -> None:
    p = _StubProvider()
    assert p.supports_file_type("pdf")
    assert not p.supports_file_type("png")
    assert p.supports_file_type(None)


# ── Layout registry ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_layout_registry() -> None:
    reset_layout_registry()
    yield
    reset_layout_registry()


def test_registry_has_builtin_docling() -> None:
    _ensure_registered()
    assert "docling-layout" in _PROVIDERS


def test_get_layout_provider_auto_raises_when_nothing_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.ocr import layout_registry

    monkeypatch.setattr(layout_registry.settings, "enable_docling", False)
    with pytest.raises(LayoutProviderError):
        get_layout_provider("auto")


def test_get_layout_provider_explicit_unknown() -> None:
    with pytest.raises(ValueError):
        get_layout_provider("not-a-thing")


def test_get_layout_provider_explicit_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.ocr import layout_registry

    monkeypatch.setattr(layout_registry.settings, "enable_docling", False)
    with pytest.raises(LayoutProviderError):
        get_layout_provider("docling-layout")


def test_register_layout_provider_adds_to_catalogue() -> None:
    class _Other(BaseLayoutProvider):
        @property
        def provider_id(self) -> str:
            return "other"

        @property
        def display_name(self) -> str:
            return "Other"

        async def extract_layout(self, file_path: Path) -> LayoutResult:
            return LayoutResult(text="", pages=[""], provider="other", page_count=0)

    register_layout_provider(_Other)
    assert "other" in _PROVIDERS


def test_register_layout_provider_dedups() -> None:
    # Registering the same class twice should not raise
    register_layout_provider(_StubProvider)
    register_layout_provider(_StubProvider)
    assert _PROVIDERS["stub"].display_name == "Stub"


def test_list_layout_provider_statuses_includes_user_selectable_only() -> None:
    statuses = list_layout_provider_statuses()
    assert all(isinstance(s, LayoutProviderStatus) for s in statuses)
    assert all(s.user_selectable for s in statuses)


def test_layout_auto_priority_starts_with_docling() -> None:
    assert LAYOUT_AUTO_PRIORITY[0] == "docling-layout"


def test_docling_layout_provider_unavailable_when_module_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """is_available() must return False when docling is not installed."""

    from app.services.ocr import docling_layout_provider

    monkeypatch.setattr(
        docling_layout_provider.importlib,
        "import_module",
        lambda name: (_ for _ in ()).throw(ImportError("nope")),
    )
    from app.services.ocr.docling_layout_provider import DoclingLayoutProvider

    assert DoclingLayoutProvider().is_available() is False


def test_docling_layout_provider_extract_layout_when_unavailable() -> None:
    """extract_layout must raise a typed error when the engine is not installed."""

    from app.services.ocr.docling_layout_provider import DoclingLayoutProvider

    provider = DoclingLayoutProvider()
    # If docling is not installed (which it isn't in CI), is_available is False
    if not provider.is_available():
        import asyncio

        with pytest.raises(LayoutProviderError):
            asyncio.run(provider.extract_layout(Path("/tmp/fake.pdf")))
