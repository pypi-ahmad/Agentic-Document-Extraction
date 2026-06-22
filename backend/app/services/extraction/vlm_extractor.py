"""VLM-as-extractor path: skip OCR, send the image straight to a
vision-language model.

The default extraction pipeline is OCR-then-LLM: the OCR engine
(``paddleocr``, ``docling``, ``glm-ocr``, ``pymupdf``) turns the
document into plain text, and the LLM extracts structured
fields from that text. This works for most documents but is
suboptimal for tables, charts, and complex layouts where the
VLM can see structure the OCR misses.

This module implements the VLM-as-extractor alternative: the
document (image or PDF page) is sent directly to a vision-
language model — PaddleOCR-VL-1.6 by default, or any
Ollama-served VLM (e.g. ``glm-ocr`` used in VLM mode) — and the
VLM returns the structured JSON in one shot.

When to use
-----------

- **Tables and complex layouts**: a VLM can read a 5x5 invoice
  line-items table directly from the image; the OCR
  pipeline often jumbles column order.
- **Scanned forms**: VLMs handle checkboxes, handwritten
  annotations, and stamp overlays better than OCR.
- **Single-page documents**: the latency win from skipping OCR
  is significant (one model call instead of OCR + LLM).

When NOT to use
---------------

- **Long multi-page documents**: most VLMs cap at 1-4 pages of
  context. The OCR path is still the right choice for 50-page
  financial reports.
- **High-volume cheap extraction**: VLMs are 5-20x more
  expensive than the OCR + small-LLM path. Use the LLM judge
  (Commit 6) to confirm the VLM path is worth the cost.

Install
-------

- PaddleOCR-VL: ``pip install paddleocr-vl>=1.6`` (or the
  ``ade[vlm]`` extra).
- GLM-OCR-as-VLM: GLM-OCR is already a vision model, so
  pointing ``enable_vlm_extract`` at the local Ollama endpoint
  reuses the existing install.
- Any other VLM: implement a new client in this module;
  the registry pattern keeps it drop-in.

Configuration
-------------

- ``enable_vlm_extract: bool = False`` — flips the VLM path on
  for the routes that opt in (``POST /api/extractions`` with
  ``extractor=vlm``).
- ``vlm_default_model: str = "paddleocr-vl"`` — the model
  identifier sent to the chosen client.
- ``vlm_ollama_model: str = "glm-ocr:latest"`` — alternate
  backend; used when ``vlm_default_model == "ollama"``.
- ``vlm_max_tokens: int = 2048`` — output cap.
- ``vlm_timeout_seconds: float = 120.0``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.logging_setup import get_logger
from app.services.llm.prompts_loader import load_prompt

logger = get_logger("app.vlm")

VLM_VERSION = "vlm-1"
"""Bump when the prompt template or the VLM calling convention changes."""


@dataclass
class VLMResult:
    """The structured output of one VLM call.

    Mirrors the LLM provider's :class:`ExtractionResult` shape
    so the downstream pipeline (validation, reflection) does
    not need to special-case the source.
    """

    data: dict[str, Any]
    raw_response: str
    model_used: str
    provider: str
    confidence: dict[str, float] = field(default_factory=dict)
    latency_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "data": self.data,
            "raw_response": self.raw_response,
            "model_used": self.model_used,
            "provider": self.provider,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
        }


# ── Clients ─────────────────────────────────────────────────────────


def is_available() -> bool:
    """Return True when at least one VLM backend is reachable."""
    if not settings.enable_vlm_extract:
        return False
    if settings.vlm_default_model == "ollama":
        return True  # Ollama is local; the call itself fails fast if down.
    if settings.vlm_default_model == "paddleocr-vl":
        try:
            import paddleocr_vl  # noqa: F401  # type: ignore[import-untyped]

            return True
        except ImportError:
            return False
    return True  # Custom client: trust the user's config.


async def _call_paddleocr_vl(
    *,
    file_path: Path,
    schema_fields: list[dict],
    client: httpx.AsyncClient | None = None,
) -> VLMResult:
    """Call the PaddleOCR-VL-1.6 client.

    The actual call is left to a future commit that adds the
    paddleocr-vl dependency; this stub returns a clearly
    failed result so callers can fall back to the OCR path
    gracefully.
    """
    try:
        from paddleocr_vl import PaddleOCRVL  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "paddleocr-vl is not installed; run `pip install paddleocr-vl>=1.6` "
            "or use the ``ade[vlm]`` extra."
        ) from exc

    vl = PaddleOCRVL()
    prompt = load_prompt("extraction", "v1").render(
        text="",  # VLM sees the image; no OCR text to pass.
        fields_block=_fields_block(schema_fields),
    )
    t0 = time.perf_counter()
    response = await vl.predict(image=str(file_path), prompt=prompt)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return _parse_vlm_response(
        response,
        model_used=settings.vlm_default_model,
        provider="paddleocr-vl",
        latency_ms=latency_ms,
    )


async def _call_ollama_vlm(
    *,
    file_path: Path,
    schema_fields: list[dict],
    client: httpx.AsyncClient | None = None,
) -> VLMResult:
    """Call a local Ollama VLM (e.g. glm-ocr in chat mode)."""
    base_url = settings.ollama_base_url
    model = settings.vlm_ollama_model
    url = f"{base_url.rstrip('/')}/api/chat"
    prompt = load_prompt("extraction", "v1").render(
        text="",
        fields_block=_fields_block(schema_fields),
    )
    # Encode the file as base64 for the Ollama vision API.
    import base64

    image_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [image_b64],
            }
        ],
        "stream": False,
        "format": "json",
    }
    owns_client = client is None
    c = client if client is not None else httpx.AsyncClient(timeout=settings.vlm_timeout_seconds)
    t0 = time.perf_counter()
    try:
        resp = await c.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await c.aclose()
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return _parse_vlm_response(
        data.get("message", {}).get("content", ""),
        model_used=model,
        provider="ollama",
        latency_ms=latency_ms,
    )


def _fields_block(schema_fields: list[dict]) -> str:
    field_descriptions = []
    for f in schema_fields:
        req = "required" if f.get("required", True) else "optional"
        field_descriptions.append(
            f'  - "{f["name"]}" ({f.get("field_type", "string")}, {req}): {f.get("description", "")}'
        )
    return "\n".join(field_descriptions)


def _parse_vlm_response(
    raw: str,
    *,
    model_used: str,
    provider: str,
    latency_ms: int,
) -> VLMResult:
    """Parse the VLM's JSON response into a :class:`VLMResult`."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("vlm.parse_failed: %r", raw[:200])
        data = {}
    if not isinstance(data, dict):
        data = {}
    # Pull the _confidence block out (regardless of its type — we
    # only use it when it's actually a dict, but always remove it
    # from the payload so the iteration below only sees real fields).
    raw_conf = data.pop("_confidence", None)
    confidence: dict[str, float] = (
        {k: float(v) for k, v in raw_conf.items() if isinstance(k, str)}
        if isinstance(raw_conf, dict)
        else {}
    )
    # Default confidence to 0.5 for every field the VLM did return,
    # to keep the routing logic working even when the VLM omits
    # the _confidence block.
    for k in data:
        confidence.setdefault(k, 0.5)
    return VLMResult(
        data=data,
        raw_response=raw,
        model_used=model_used,
        provider=provider,
        confidence=confidence,
        latency_ms=latency_ms,
    )


# ── Public API ──────────────────────────────────────────────────────


async def extract_with_vlm(
    *,
    file_path: Path,
    schema_fields: list[dict],
    client: httpx.AsyncClient | None = None,
) -> VLMResult:
    """Run the VLM-as-extractor and return a :class:`VLMResult`.

    Routes to the configured backend (``vlm_default_model``).
    Raises ``RuntimeError`` when VLM is disabled or the chosen
    backend is not available; the caller is expected to fall
    back to the OCR path.
    """
    if not is_available():
        raise RuntimeError("VLM extraction is disabled or unavailable")
    model = settings.vlm_default_model
    if model == "ollama":
        return await _call_ollama_vlm(
            file_path=file_path, schema_fields=schema_fields, client=client
        )
    if model == "paddleocr-vl":
        return await _call_paddleocr_vl(
            file_path=file_path, schema_fields=schema_fields, client=client
        )
    # Custom: try the Ollama path with the configured model name.
    return await _call_ollama_vlm(file_path=file_path, schema_fields=schema_fields, client=client)


__all__ = [
    "VLM_VERSION",
    "VLMResult",
    "extract_with_vlm",
    "is_available",
]
