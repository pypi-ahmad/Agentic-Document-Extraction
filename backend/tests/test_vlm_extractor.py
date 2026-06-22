"""Tests for the VLM-as-extractor module.

Covers:

- is_available respects the enable_vlm_extract flag.
- The Ollama VLM path with a mocked httpx transport.
- The PaddleOCR-VL path: import-missing error is raised with a
  useful message.
- _parse_vlm_response handles well-formed JSON, code-fenced
  JSON, garbage, and missing _confidence.
- extract_with_vlm dispatches by settings.vlm_default_model.
- The VLMResult dataclass shape.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.services.extraction import vlm_extractor as vlm_mod
from app.services.extraction.vlm_extractor import (
    VLMResult,
    _parse_vlm_response,
    extract_with_vlm,
    is_available,
)

# ── is_available ────────────────────────────────────────────────────


def test_is_available_false_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", False)
    assert is_available() is False


def test_is_available_true_when_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", True)
    monkeypatch.setattr("app.config.settings.vlm_default_model", "ollama")
    assert is_available() is True


def test_is_available_paddleocr_vl_when_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", True)
    monkeypatch.setattr("app.config.settings.vlm_default_model", "paddleocr-vl")
    # Stash a fake module so the import inside is_available succeeds.
    import types

    monkeypatch.setitem(sys.modules, "paddleocr_vl", types.ModuleType("paddleocr_vl"))
    assert is_available() is True


def test_is_available_paddleocr_vl_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", True)
    monkeypatch.setattr("app.config.settings.vlm_default_model", "paddleocr-vl")
    # Force the import to fail by removing the module and patching
    # __import__ to raise on any attempt to load it.
    monkeypatch.delitem(sys.modules, "paddleocr_vl", raising=False)
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "paddleocr_vl" or name.startswith("paddleocr_vl."):
            raise ImportError("fake: missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Re-check after the patch is in place: the function is defined
    # in the module's namespace, so this lookup is the one is_available
    # uses.
    from app.services.extraction.vlm_extractor import is_available as fresh_ia

    assert fresh_ia() is False


# ── _parse_vlm_response ─────────────────────────────────────────────


def test_parse_vlm_response_well_formed() -> None:
    raw = json.dumps(
        {
            "vendor": "Acme",
            "total": 500,
            "_confidence": {"vendor": 0.9, "total": 0.8},
        }
    )
    r = _parse_vlm_response(raw, model_used="m", provider="p", latency_ms=10)
    assert r.data == {"vendor": "Acme", "total": 500}
    assert r.confidence == {"vendor": 0.9, "total": 0.8}
    assert r.model_used == "m"
    assert r.provider == "p"
    assert r.latency_ms == 10


def test_parse_vlm_response_strips_code_fence() -> None:
    raw = "```json\n" + json.dumps({"vendor": "Acme"}) + "\n```"
    r = _parse_vlm_response(raw, model_used="m", provider="p", latency_ms=0)
    assert r.data == {"vendor": "Acme"}


def test_parse_vlm_response_handles_garbage() -> None:
    r = _parse_vlm_response("not json", model_used="m", provider="p", latency_ms=0)
    assert r.data == {}


def test_parse_vlm_response_default_confidence_for_missing() -> None:
    """When the VLM returns a field but no _confidence, default to 0.5."""
    raw = json.dumps({"vendor": "Acme"})
    r = _parse_vlm_response(raw, model_used="m", provider="p", latency_ms=0)
    assert r.confidence == {"vendor": 0.5}


def test_parse_vlm_response_handles_non_dict_confidence() -> None:
    """A non-dict _confidence is ignored, fields default to 0.5."""
    raw = json.dumps({"vendor": "Acme", "_confidence": "not a dict"})
    r = _parse_vlm_response(raw, model_used="m", provider="p", latency_ms=0)
    assert r.data == {"vendor": "Acme"}
    assert r.confidence == {"vendor": 0.5}


# ── VLMResult.to_dict ───────────────────────────────────────────────


def test_vlm_result_to_dict_roundtrip() -> None:
    r = VLMResult(
        data={"vendor": "Acme"},
        raw_response="x",
        model_used="m",
        provider="p",
        confidence={"vendor": 0.9},
        latency_ms=10,
    )
    d = r.to_dict()
    assert d["data"] == {"vendor": "Acme"}
    assert d["model_used"] == "m"


# ── extract_with_vlm: Ollama path with mocked transport ────────────


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(200, json=self.payload)


@pytest.mark.asyncio
async def test_extract_with_vlm_ollama(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", True)
    monkeypatch.setattr("app.config.settings.vlm_default_model", "ollama")
    monkeypatch.setattr("app.config.settings.ollama_base_url", "http://mock:11434")
    monkeypatch.setattr("app.config.settings.vlm_ollama_model", "glm-ocr:latest")

    payload = {
        "message": {
            "content": json.dumps(
                {
                    "vendor": "Acme",
                    "total": 500,
                    "_confidence": {"vendor": 0.9, "total": 0.8},
                }
            )
        }
    }
    transport = _MockTransport(payload)
    client = httpx.AsyncClient(transport=transport, base_url="http://mock:11434")
    f = tmp_path / "x.png"
    f.write_bytes(b"\x89PNG")
    r = await extract_with_vlm(
        file_path=f,
        schema_fields=[{"name": "vendor", "field_type": "string", "required": True}],
        client=client,
    )
    await client.aclose()
    assert r.data == {"vendor": "Acme", "total": 500}
    assert r.provider == "ollama"
    # The transport captured the request — check that the image was
    # base64-encoded in the body.
    assert transport.last_request is not None
    body = json.loads(transport.last_request.content)
    assert "messages" in body
    msg = body["messages"][0]
    assert msg["images"] == [base64.b64encode(b"\x89PNG").decode("ascii")]


@pytest.mark.asyncio
async def test_extract_with_vlm_paddleocr_vl_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", True)
    monkeypatch.setattr("app.config.settings.vlm_default_model", "paddleocr-vl")
    monkeypatch.delitem(sys.modules, "paddleocr_vl", raising=False)
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "paddleocr_vl" or name.startswith("paddleocr_vl."):
            raise ImportError("fake: missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Patch the module's is_available so the gate passes.

    monkeypatch.setattr(vlm_mod, "is_available", lambda: True)
    f = tmp_path / "x.png"
    f.write_bytes(b"\x89PNG")
    with pytest.raises(RuntimeError, match="paddleocr-vl"):
        await extract_with_vlm(file_path=f, schema_fields=[])


@pytest.mark.asyncio
async def test_extract_with_vlm_disabled_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("app.config.settings.enable_vlm_extract", False)
    f = tmp_path / "x.png"
    f.write_bytes(b"\x89PNG")
    with pytest.raises(RuntimeError, match="disabled"):
        await extract_with_vlm(file_path=f, schema_fields=[])
