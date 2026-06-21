"""Unit tests for the GLM-OCR (local Ollama) OCR provider."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from app.config import settings
from app.services.ocr.glm_ocr_provider import (
    GLMOCRProvider,
    _clean_glm_ocr_text,
)
from app.services.ocr.registry import get_ocr_provider, list_ocr_provider_statuses

# ── Text-cleanup helper ─────────────────────────────────────────────


def test_clean_text_strips_layout_markup():
    raw = (
        "Invoice #12345\n"
        "Date: 2026-06-22\n"
        "Total: $1,234.56</invoice>\n"
        "<table><tr><td></td></tr></table>"
    )
    assert _clean_glm_ocr_text(raw) == ("Invoice #12345\nDate: 2026-06-22\nTotal: $1,234.56")


def test_clean_text_strips_html_comments_and_collapses_blank_lines():
    raw = "Hello<!-- comment -->world\n\n\n\nAgain"
    assert _clean_glm_ocr_text(raw) == "Helloworld\n\nAgain"


def test_clean_text_handles_empty_and_passthrough():
    assert _clean_glm_ocr_text("") == ""
    assert _clean_glm_ocr_text("plain text only") == "plain text only"


# ── Provider identity / metadata ─────────────────────────────────────


def test_provider_metadata():
    p = GLMOCRProvider()
    assert p.provider_id == "glmocr"
    assert p.display_name == "GLM-OCR (local Ollama)"
    assert p.feature_flag_name == "enable_glm_ocr"
    assert p.is_user_selectable is True
    assert p.supported_file_types == frozenset({"png", "jpeg", "tiff"})


def test_provider_pdf_unsupported():
    p = GLMOCRProvider()
    assert not p.supports_file_type("pdf")


# ── Availability probe ───────────────────────────────────────────────


def _mock_tags_response(model: str | None) -> httpx.Response:
    if model is None:
        body: dict = {"models": []}
    else:
        body = {"models": [{"name": model}]}
    return httpx.Response(200, json=body)


def test_is_available_true_when_model_present():
    p = GLMOCRProvider()
    with patch("httpx.Client.get", return_value=_mock_tags_response(settings.ollama_glm_ocr_model)):
        assert p.is_available() is True


def test_is_available_false_when_model_missing():
    p = GLMOCRProvider()
    with patch("httpx.Client.get", return_value=_mock_tags_response("some-other-model:latest")):
        assert p.is_available() is False


def test_is_available_false_on_connection_error():
    p = GLMOCRProvider()
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("nope")):
        assert p.is_available() is False


def test_is_available_false_on_non_200_status():
    p = GLMOCRProvider()
    bad = httpx.Response(503, text="service unavailable")
    with patch("httpx.Client.get", return_value=bad):
        assert p.is_available() is False


# ── Feature flag + registry integration ──────────────────────────────


def test_provider_flag_default_off(monkeypatch):
    monkeypatch.setattr(settings, "enable_glm_ocr", False)
    statuses = list_ocr_provider_statuses()
    glm = next(s for s in statuses if s.provider_id == "glmocr")
    assert glm.enabled is False
    # But it should still appear in the user-selectable list.
    assert glm.user_selectable is True


def test_explicit_glmocr_disabled_raises(monkeypatch):
    monkeypatch.setattr(settings, "enable_glm_ocr", False)
    with pytest.raises(Exception):
        # OCRProviderUnavailableError is raised when the requested engine
        # is disabled by config.
        get_ocr_provider("glmocr")


# ── extract_text end-to-end with mocked HTTP ─────────────────────────


def test_extract_text_happy_path(tmp_path: Path, monkeypatch):
    # Enable the flag so the registry can route to GLM-OCR.
    monkeypatch.setattr(settings, "enable_glm_ocr", True)
    monkeypatch.setattr(settings, "glm_ocr_timeout_seconds", 5.0)

    img = tmp_path / "invoice.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # tiny stand-in PNG

    ollama_response = {
        "model": "glm-ocr:latest",
        "response": "Hello<!--c--> world</invoice><table><tr></tr></table>",
        "done": True,
        "eval_count": 17,
        "prompt_eval_count": 8,
    }

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url, json):
            request = httpx.Request("POST", url)
            return httpx.Response(200, json=ollama_response, request=request)

    monkeypatch.setattr("app.services.ocr.glm_ocr_provider.httpx.AsyncClient", _FakeAsyncClient)

    p = GLMOCRProvider()
    result = await_p(p.extract_text(img))
    assert "Hello world" in result.text
    assert "</invoice>" not in result.text
    assert "<table>" not in result.text
    assert result.provider == "glmocr"
    assert result.raw and result.raw["model"] == "glm-ocr:latest"


def test_extract_text_raises_on_empty_response(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(settings, "enable_glm_ocr", True)

    img = tmp_path / "blank.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a) -> None:
            return None

        async def post(self, url, json):
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"response": ""}, request=request)

    monkeypatch.setattr("app.services.ocr.glm_ocr_provider.httpx.AsyncClient", _FakeAsyncClient)

    p = GLMOCRProvider()
    with pytest.raises(Exception) as exc_info:
        await_p(p.extract_text(img))
    assert "no text" in str(exc_info.value).lower()


# ── helpers ──────────────────────────────────────────────────────────


def await_p(coro):
    """Run an awaitable to completion (for async test bodies)."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)
