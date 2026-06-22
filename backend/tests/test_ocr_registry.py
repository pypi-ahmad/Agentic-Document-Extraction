"""Tests for OCR registry, routing policy, and result types."""

from __future__ import annotations

import builtins
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.ocr.base import (
    BaseOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProviderError,
    OCRProviderUnavailableError,
    OCRResult,
    OCRTable,
)
from app.services.ocr.registry import (
    get_ocr_provider,
    list_ocr_provider_statuses,
    list_ocr_providers,
    register_provider,
    reset_registry,
)

# ── Result-type tests ───────────────────────────────────────────────


def test_ocr_result_minimal():
    """OCRResult with only mandatory fields."""
    r = OCRResult(text="hello", pages=["hello"], provider="test")
    assert r.text == "hello"
    assert r.pages == ["hello"]
    assert r.provider == "test"
    assert len(r.page_results) == 1
    assert r.page_results[0].text == "hello"
    assert r.blocks == []
    assert r.tables == []
    assert r.confidence is None
    assert r.raw is None
    assert r.metadata is None
    assert r.regions == []


def test_ocr_result_with_structured_pages():
    """OCRResult with enriched page_results."""
    block = OCRBlock(text="cell", bbox=(0, 0, 100, 20), confidence=0.95)
    table = OCRTable(cells=[["a", "b"], ["c", "d"]], page_index=0)
    page = OCRPageResult(
        page_index=0,
        text="cell",
        blocks=[block],
        tables=[table],
        confidence=0.95,
    )
    r = OCRResult(
        text="cell",
        pages=["cell"],
        provider="test",
        page_results=[page],
        confidence=0.95,
        raw={"engine_version": "1.0"},
    )
    assert len(r.page_results) == 1
    assert r.page_results[0].blocks[0].confidence == 0.95
    assert r.page_results[0].tables[0].cells == [["a", "b"], ["c", "d"]]
    assert r.blocks == [block]
    assert r.tables == [table]
    assert r.regions == [block]
    assert r.raw == {"engine_version": "1.0"}
    assert r.metadata == {"engine_version": "1.0"}


def test_ocr_result_accepts_legacy_metadata_alias():
    """Older callers using metadata should still get normalized raw output."""

    r = OCRResult(
        text="legacy",
        pages=["legacy"],
        provider="legacy",
        metadata={"old": True},
    )

    assert r.raw == {"old": True}
    assert r.metadata == {"old": True}


def test_ocr_block_defaults():
    b = OCRBlock(text="word")
    assert b.bbox is None
    assert b.confidence is None
    assert b.label == ""


def test_ocr_table_defaults():
    t = OCRTable(cells=[["x"]])
    assert t.bbox is None
    assert t.page_index == 0


# ── Registry list / lookup ──────────────────────────────────────────


def test_list_providers():
    providers = list_ocr_providers()
    assert len(providers) >= 2  # pymupdf + paddleocr
    assert all(isinstance(p, BaseOCRProvider) for p in providers)
    ids = {p.provider_id for p in providers}
    assert "pymupdf" in ids
    assert "paddleocr" in ids


def test_list_provider_statuses_excludes_internal_fallback_by_default():
    statuses = list_ocr_provider_statuses()
    ids = [status.provider_id for status in statuses]
    assert "pymupdf" not in ids
    # User-selectable engines (auto never appears in this list).
    # Docling joined the list in v0.4.0 (Commit 9).
    assert ids == ["glmocr", "paddleocr", "docling"]


def test_get_pymupdf():
    provider = get_ocr_provider("pymupdf")
    assert provider.provider_id == "pymupdf"
    assert provider.display_name == "Built-in PDF reader (PyMuPDF)"


def test_get_unknown_provider():
    with pytest.raises(ValueError, match="Unknown OCR provider"):
        get_ocr_provider("nonexistent")


# ── Auto routing ────────────────────────────────────────────────────


def test_auto_resolves_to_available_provider():
    """Auto should always return an available provider."""
    provider = get_ocr_provider("auto", file_path=Path("sample.pdf"))
    assert provider.is_available()


def test_auto_uses_builtin_pdf_reader_for_pdf_when_image_ocr_is_unavailable():
    """When no OCR engine is enabled/available, PDF Auto falls back to PyMuPDF."""
    # By default in tests, PaddleOCR is not available/installed
    provider = get_ocr_provider("auto", file_path=Path("sample.pdf"))
    assert provider.provider_id == "pymupdf"


def test_auto_prefers_builtin_pdf_reader_for_pdf_even_when_paddleocr_is_ready():
    """PDF Auto stays on the built-in PDF reader; PaddleOCR is image-only."""

    class FakePaddle(BaseOCRProvider):
        feature_flag_name = "enable_paddleocr"
        supported_file_types = frozenset({"png", "jpeg", "tiff"})

        @property
        def provider_id(self) -> str:
            return "paddleocr"

        @property
        def display_name(self) -> str:
            return "Fake PaddleOCR"

        async def extract_text(self, file_path: Path) -> OCRResult:
            return OCRResult(text="", pages=[], provider=self.provider_id)

        def is_available(self) -> bool:
            return True

    from app.services.ocr import registry

    original = registry._PROVIDERS.get("paddleocr")
    try:
        registry._PROVIDERS["paddleocr"] = FakePaddle()
        with patch.object(registry.settings, "enable_paddleocr", True):
            provider = get_ocr_provider("auto", file_path=Path("sample.pdf"))
            assert provider.provider_id == "pymupdf"
    finally:
        if original is not None:
            registry._PROVIDERS["paddleocr"] = original


def test_auto_rejects_image_when_only_pdf_fallback_exists():
    """Auto should fail clearly for image inputs if no image OCR engine is ready."""

    with pytest.raises(OCRProviderUnavailableError, match="will not fall back"):
        get_ocr_provider("auto", file_path=Path("scan.png"))


def test_auto_prefers_paddleocr_when_enabled_and_available():
    """If PaddleOCR is both enabled AND available, Auto picks it first."""

    class FakePaddle(BaseOCRProvider):
        feature_flag_name = "enable_paddleocr"

        @property
        def provider_id(self) -> str:
            return "paddleocr"

        @property
        def display_name(self) -> str:
            return "Fake PaddleOCR"

        async def extract_text(self, file_path: Path) -> OCRResult:
            return OCRResult(text="", pages=[], provider=self.provider_id)

        def is_available(self) -> bool:
            return True

    from app.services.ocr import registry

    original = registry._PROVIDERS.get("paddleocr")
    try:
        registry._PROVIDERS["paddleocr"] = FakePaddle()
        with patch.object(registry.settings, "enable_paddleocr", True):
            provider = get_ocr_provider("auto", file_path=Path("scan.png"))
            assert provider.provider_id == "paddleocr"
    finally:
        if original is not None:
            registry._PROVIDERS["paddleocr"] = original


def test_explicit_pymupdf_rejects_non_pdf_input():
    """The internal PyMuPDF fallback should not be treated as an image OCR engine."""

    with pytest.raises(OCRProviderUnavailableError, match="does not safely support 'png'"):
        get_ocr_provider("pymupdf", file_path=Path("scan.png"))


def test_explicit_paddleocr_rejects_pdf_input():
    """PaddleOCR is exposed as image OCR only in the current user-facing contract."""

    with (
        patch(
            "app.services.ocr.paddleocr_provider.PaddleOCRProvider.is_available", return_value=True
        ),
        patch("app.services.ocr.registry.settings.enable_paddleocr", True),
    ):
        with pytest.raises(OCRProviderUnavailableError, match="does not safely support 'pdf'"):
            get_ocr_provider("paddleocr", file_path=Path("sample.pdf"))


def test_paddleocr_availability_probe_treats_native_import_failure_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    """Import-time native library errors must not crash provider/status listing.

    This test is skipped when paddleocr is actually installed (e.g. in CI),
    since the mock cannot override an already-imported module.
    """
    # Skip if paddleocr is already importable (e.g. in CI)
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("paddleocr is installed, cannot test import failure")

    from app.services.ocr.paddleocr_provider import PaddleOCRProvider

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "paddleocr":
            raise OSError("missing native dependency")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert PaddleOCRProvider().is_available() is False


# ── Plugin registration ────────────────────────────────────────────


def test_register_custom_provider():
    """register_provider() allows adding new engines at runtime."""

    class CustomProvider(BaseOCRProvider):
        @property
        def provider_id(self) -> str:
            return "custom_test_engine"

        @property
        def display_name(self) -> str:
            return "Custom Test"

        async def extract_text(self, file_path: Path) -> OCRResult:
            return OCRResult(text="custom", pages=["custom"], provider=self.provider_id)

    from app.services.ocr import registry

    try:
        registry._PROVIDERS.clear()
        registry._PROVIDER_CLASSES.clear()
        register_provider(CustomProvider)
        ids = {provider.provider_id for provider in list_ocr_providers()}
        assert "pymupdf" in ids
        p = get_ocr_provider("custom_test_engine")
        assert p.provider_id == "custom_test_engine"
    finally:
        registry._PROVIDERS.pop("custom_test_engine", None)
        reset_registry()


# ── Error types ─────────────────────────────────────────────────────


def test_ocr_provider_error_message():
    err = OCRProviderError("test", "something broke")
    assert str(err) == "[test] something broke"
    assert err.provider == "test"


def test_unavailable_error_is_provider_error():
    """OCRProviderUnavailableError is a subclass of OCRProviderError."""
    err = OCRProviderUnavailableError("x", "not installed")
    assert isinstance(err, OCRProviderError)
