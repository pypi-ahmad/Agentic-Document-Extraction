"""Tests for the PaddleOCR provider's 3.x / 2.x dual-API support.

Covers:

- The version detection helper.
- The 3.x ``predict()`` path (list-of-dicts return).
- The 2.x ``ocr()`` legacy path (list-of-lists return).
- The ``PADDLEOCR_USE_V2`` env-var override.
- Empty / None page handling.
- ``is_available`` when the package is not installed.
- Confidence averaging and bbox construction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.services.ocr import paddleocr_provider as provider_mod
from app.services.ocr.paddleocr_provider import (
    PaddleOCRProvider,
    _paddleocr_version,
)

# ── _paddleocr_version ──────────────────────────────────────────────


def test_paddleocr_version_when_uninstalled(monkeypatch: pytest.MonkeyPatch) -> None:
    """When paddleocr is not importable, version is (0, 0, 0).

    This test is skipped when paddleocr is actually installed (e.g. in CI),
    since the mock cannot override an already-imported module.
    """
    # Skip if paddleocr is already importable (e.g. in CI)
    try:
        import paddleocr  # noqa: F401
    except ImportError:
        pass
    else:
        pytest.skip("paddleocr is installed, cannot test uninstalled version")

    monkeypatch.setattr(
        provider_mod,
        "importlib",
        _FakeImportModule(raise_on=("paddleocr",)),
    )
    assert _paddleocr_version() == (0, 0, 0)


def test_paddleocr_version_parses_semver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Version is parsed as (major, minor, patch) integers."""
    # Stub the import by installing a fake paddleocr module.
    import sys
    import types

    fake = types.ModuleType("paddleocr")
    fake.__version__ = "3.7.1"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "paddleocr", fake)
    assert _paddleocr_version() == (3, 7, 1)


# ── 3.x path ─────────────────────────────────────────────────────────


class _FakePredictOcr3:
    """Mimics PaddleOCR 3.x: ``predict(path)`` returns list of dicts."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def predict(self, file_path: str) -> list[dict[str, Any]]:
        return [
            {
                "rec_texts": ["Hello", "World"],
                "rec_scores": [0.95, 0.85],
                "rec_polys": [
                    [[10.0, 20.0], [100.0, 20.0], [100.0, 40.0], [10.0, 40.0]],
                    [[10.0, 50.0], [100.0, 50.0], [100.0, 70.0], [10.0, 70.0]],
                ],
            }
        ]


class _FakePaddleOcr3Module:
    PaddleOCR = _FakePredictOcr3


@pytest.mark.asyncio
async def test_extract_v3_returns_ocr_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(provider_mod, "_paddleocr_version", lambda: (3, 7, 1))
    monkeypatch.setattr(
        "app.services.ocr.paddleocr_provider.PaddleOCR",
        _FakePredictOcr3,
        raising=False,
    )
    # Replace the import in the function body.
    monkeypatch.setitem(__import__("sys").modules, "paddleocr", _FakePaddleOcr3Module())

    p = PaddleOCRProvider()
    file = tmp_path / "x.png"
    file.write_bytes(b"\x89PNG")
    result = await p.extract_text(file)
    assert result.provider == "paddleocr"
    assert "Hello" in result.text
    assert "World" in result.text
    assert result.confidence is not None
    assert 0 < result.confidence <= 1
    assert result.raw is not None
    assert result.raw["engine"] == "paddleocr-3"
    # Two blocks, both with bbox.
    assert len(result.page_results) == 1
    assert len(result.page_results[0].blocks) == 2
    assert result.page_results[0].blocks[0].bbox == (10.0, 20.0, 100.0, 40.0)


@pytest.mark.asyncio
async def test_extract_v3_handles_empty_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _EmptyOcr:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

        def predict(self, file_path: str) -> list[dict[str, Any]]:
            return [{}]

    monkeypatch.setattr(provider_mod, "_paddleocr_version", lambda: (3, 7, 1))
    import sys
    import types

    mod = types.ModuleType("paddleocr")
    mod.PaddleOCR = _EmptyOcr  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "paddleocr", mod)

    p = PaddleOCRProvider()
    file = tmp_path / "x.png"
    file.write_bytes(b"\x89PNG")
    result = await p.extract_text(file)
    assert result.text == ""
    assert result.confidence is None


# ── 2.x legacy path ────────────────────────────────────────────────


class _FakeOcr2:
    """Mimics PaddleOCR 2.x: ``ocr(path, cls=True)`` returns list-of-lists."""

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    def ocr(self, file_path: str, cls: bool = True) -> list[list[Any]]:
        return [
            [
                [
                    [[10.0, 20.0], [100.0, 20.0], [100.0, 40.0], [10.0, 40.0]],
                    ("Hello", 0.95),
                ],
                [
                    [[10.0, 50.0], [100.0, 50.0], [100.0, 70.0], [10.0, 70.0]],
                    ("World", 0.85),
                ],
            ]
        ]


@pytest.mark.asyncio
async def test_extract_v2_returns_ocr_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(provider_mod, "_paddleocr_version", lambda: (2, 7, 0))
    import sys
    import types

    mod = types.ModuleType("paddleocr")
    mod.PaddleOCR = _FakeOcr2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "paddleocr", mod)

    p = PaddleOCRProvider()
    file = tmp_path / "x.png"
    file.write_bytes(b"\x89PNG")
    result = await p.extract_text(file)
    assert "Hello" in result.text
    assert result.raw is not None
    assert result.raw["engine"] == "paddleocr-2"
    assert "paddleocr 2.x" in p.display_name.lower()


# ── Override: PADDLEOCR_USE_V2 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_use_v2_env_forces_legacy_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When PADDLEOCR_USE_V2=1 and paddleocr 3.x is installed,
    the legacy v2 path is taken."""
    monkeypatch.setattr(provider_mod, "_paddleocr_version", lambda: (3, 7, 1))
    monkeypatch.setenv("PADDLEOCR_USE_V2", "1")
    import sys
    import types

    mod = types.ModuleType("paddleocr")
    mod.PaddleOCR = _FakeOcr2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "paddleocr", mod)

    p = PaddleOCRProvider()
    file = tmp_path / "x.png"
    file.write_bytes(b"\x89PNG")
    result = await p.extract_text(file)
    assert result.raw["engine"] == "paddleocr-2"


# ── is_available ───────────────────────────────────────────────────


def test_is_available_false_when_uninstalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        provider_mod,
        "importlib",
        _FakeImportModule(raise_on=("paddleocr",)),
    )
    assert PaddleOCRProvider().is_available() is False


# ── Helpers ─────────────────────────────────────────────────────────


class _FakeImportModule:
    def __init__(self, *, raise_on: tuple[str, ...] = ()) -> None:
        self.raise_on = raise_on
        self._real = __import__("importlib")

    def import_module(self, name: str) -> Any:
        if name in self.raise_on:
            raise ImportError(f"fake: cannot import {name}")
        return self._real.import_module(name)
