"""Tests for the Docling provider.

Covers:

- ``is_available`` when the package is not installed.
- ``extract_text`` happy path (mocked Docling client) with both
  per-page and fallback single-page output.
- Provider is registered in the OCR registry with the right
  feature-flag and supported file types.
- ``AUTO_PRIORITY`` includes ``docling``.
- Provider is filtered out of the user-facing list when the
  ``enable_docling`` flag is off.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from app.models.enums import ParserEngine
from app.services.ocr import docling_provider as provider_mod
from app.services.ocr.docling_provider import DoclingProvider

# ── is_available ────────────────────────────────────────────────────


def test_is_available_false_when_uninstalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_mod,
        "importlib",
        _FakeImportModule(raise_on=("docling",)),
    )
    assert DoclingProvider().is_available() is False


# ── extract_text happy path ────────────────────────────────────────


class _FakePage:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeDocument:
    def __init__(self, pages: list[Any] | None, text: str = "") -> None:
        self.pages = pages or []
        self._text = text

    def export_to_markdown(self) -> str:
        if self.pages:
            return "\n\n".join(getattr(p, "text", "") for p in self.pages)
        return self._text


class _FakeConversionResult:
    def __init__(self, document: Any) -> None:
        self.document = document


class _FakeConverter:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def convert(self, file_path: str) -> _FakeConversionResult:
        # Per-page fallback: the test sets the module attribute.
        return _FakeConversionResult(_FakeDocument(pages=_PAGES_TO_RETURN, text=_TEXT_FALLBACK))


_PAGES_TO_RETURN: list[Any] = []
_TEXT_FALLBACK = ""


@pytest.mark.asyncio
async def test_extract_text_per_page(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    global _PAGES_TO_RETURN, _TEXT_FALLBACK
    _PAGES_TO_RETURN = [_FakePage("Page 1"), _FakePage("Page 2")]
    _TEXT_FALLBACK = "ignored when pages present"

    monkeypatch.setattr(provider_mod, "importlib", _FakeImportModule())  # docling "installed"
    monkeypatch.setitem(sys.modules, "docling", _FakeDoclingModule(_FakeConverter))

    p = DoclingProvider()
    file = tmp_path / "doc.pdf"
    file.write_bytes(b"%PDF-1.4 test")
    result = await p.extract_text(file)
    assert result.provider == "docling"
    assert result.text == "Page 1\n\nPage 2"
    assert len(result.pages) == 2
    assert result.pages[0] == "Page 1"
    assert result.pages[1] == "Page 2"
    assert result.confidence is None  # Docling does not expose per-block conf
    assert result.raw is not None
    assert result.raw["engine"] == "docling"
    assert result.raw["page_count"] == 2


@pytest.mark.asyncio
async def test_extract_text_no_pages_falls_back_to_markdown(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    global _PAGES_TO_RETURN, _TEXT_FALLBACK
    _PAGES_TO_RETURN = []
    _TEXT_FALLBACK = "# Full document\n\nAll content here."

    monkeypatch.setattr(provider_mod, "importlib", _FakeImportModule())
    monkeypatch.setitem(sys.modules, "docling", _FakeDoclingModule(_FakeConverter))

    p = DoclingProvider()
    file = tmp_path / "x.docx"
    file.write_bytes(b"PK\x03\x04 docx")
    result = await p.extract_text(file)
    assert result.text == "# Full document\n\nAll content here."
    assert len(result.pages) == 1


@pytest.mark.asyncio
async def test_extract_text_raises_when_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        provider_mod,
        "importlib",
        _FakeImportModule(raise_on=("docling",)),
    )
    p = DoclingProvider()
    file = tmp_path / "x.png"
    file.write_bytes(b"\x89PNG")
    with pytest.raises(Exception) as exc_info:
        await p.extract_text(file)
    assert "docling" in str(exc_info.value).lower()


# ── Registry integration ────────────────────────────────────────────


def test_provider_id_is_docling() -> None:
    p = DoclingProvider()
    assert p.provider_id == "docling"
    assert p.provider_id == ParserEngine.DOCLING.value


def test_supported_file_types() -> None:
    p = DoclingProvider()
    assert "pdf" in p.supported_file_types
    assert "docx" in p.supported_file_types
    assert "png" in p.supported_file_types


def test_feature_flag_name() -> None:
    p = DoclingProvider()
    assert p.feature_flag_name == "enable_docling"


def test_docling_in_auto_priority() -> None:
    from app.services.ocr.registry import AUTO_PRIORITY

    assert "docling" in AUTO_PRIORITY


def test_docling_in_registry_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.enable_docling", True)
    from app.services.ocr import registry

    registry.reset_registry()
    statuses = registry.list_ocr_provider_statuses()
    docling = next((s for s in statuses if s.provider_id == "docling"), None)
    assert docling is not None
    assert docling.enabled is True
    assert docling.user_selectable is True


def test_docling_in_registry_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.enable_docling", False)
    from app.services.ocr import registry

    registry.reset_registry()
    statuses = registry.list_ocr_provider_statuses()
    docling = next((s for s in statuses if s.provider_id == "docling"), None)
    # When disabled, the provider is registered but ``enabled`` is False.
    assert docling is not None
    assert docling.enabled is False


# ── Helpers ─────────────────────────────────────────────────────────


class _FakeImportModule:
    def __init__(self, *, raise_on: tuple[str, ...] = ()) -> None:
        self.raise_on = raise_on
        self._real = importlib

    def import_module(self, name: str) -> Any:
        if name in self.raise_on:
            raise ImportError(f"fake: cannot import {name}")
        return self._real.import_module(name)


def _FakeDocumentConverterFactory(klass: Any) -> Any:
    """Build a stub ``docling.document_converter`` module."""

    def _module_getattr(name: str) -> Any:
        if name == "DocumentConverter":
            return klass
        raise AttributeError(name)

    mod = types.ModuleType("docling.document_converter")
    mod.__getattr__ = _module_getattr  # type: ignore[attr-defined]
    return mod


class _FakeDoclingModule(types.ModuleType):
    def __init__(self, klass: Any) -> None:
        super().__init__("docling")
        # Register ``docling.document_converter`` as a real submodule
        # so ``from docling.document_converter import DocumentConverter``
        # works. The factory module exposes DocumentConverter as a
        # top-level attribute on the submodule object.
        self.document_converter = _FakeDocumentConverterFactory(klass)
        sys.modules["docling.document_converter"] = self.document_converter
        self.__path__ = []  # mark as a package
