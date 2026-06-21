"""Local Ollama-backed GLM-OCR parser engine.

GLM-OCR is a multimodal OCR model from Zhipu AI / THUDM. This adapter
calls a local `ollama serve` endpoint (default ``http://localhost:11434``)
and treats the vision model as a true OCR backend — full-page text
recognition with implicit layout (paragraphs, headings, tables).

This provider is **opt-in**: it is only considered for routing when
``ENABLE_GLM_OCR=true`` is set in ``.env``. It is also **runtime-gated**:
if the configured Ollama endpoint is unreachable or the requested model
is not pulled locally, the engine reports itself as unavailable and the
``auto`` router falls through to the next engine.

Why a dedicated provider instead of going through the LLM extraction
node? Two reasons:
1. OCR text is the *input* to the LLM, not the LLM's job.
2. The OCR provider contract (returns ``OCRResult`` with text + blocks)
   keeps the rest of the pipeline parser-agnostic.

When GLM-OCR returns extra HTML/markup (it tends to emit an empty
``<table>`` skeleton after the text), we strip it down to the natural
language text so downstream prompts stay clean.
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

import httpx

from app.config import settings
from app.services.ocr.base import (
    BaseOCRProvider,
    OCRPageResult,
    OCRProviderError,
    OCRResult,
)

logger = logging.getLogger(__name__)


# GLM-OCR emits trailing layout tokens such as `</invoice>`, an empty
# `<table>...</table>` skeleton, and a long tail of empty markdown
# code fences after the recognized text. Trim them all so the pipeline
# prompt only sees prose.
_LAYOUT_TAG_RE = re.compile(
    r"</?(?:invoice|table|tr|td|th|thead|tbody|tfoot|caption|colgroup|col|br|hr|p|div|span)\b[^>]*>",
    re.IGNORECASE,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Stray HTML or markdown opener/closer lines containing only ``` / <...> with no body
_EMPTY_FENCE_LINE_RE = re.compile(r"^\s*```(?:[a-zA-Z0-9_+\-]*)?\s*$", re.MULTILINE)
_EMPTY_TAG_LINE_RE = re.compile(r"^\s*<[A-Za-z][^>]*>\s*$", re.MULTILINE)
_MULTI_BLANK_RE = re.compile(r"\n{3,}")


def _dedupe_repeated_blocks(text: str) -> str:
    """Remove a verbatim repeat of the same content that GLM-OCR sometimes emits.

    The model occasionally prints the same transcription twice in a row. We
    detect that pattern by splitting on blank-line groups and dropping any
    trailing tail that exactly matches an earlier contiguous span.
    """
    if not text:
        return text
    # Split on one or more blank lines into blocks.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if len(blocks) < 2:
        return text

    # Walk from the end and drop a trailing block that exactly matches an
    # earlier block. Repeat until no more duplicates can be removed.
    changed = True
    while changed:
        changed = False
        last = blocks[-1]
        for i in range(len(blocks) - 1):
            if blocks[i] == last and i != len(blocks) - 1:
                blocks.pop()
                changed = True
                break

    return "\n\n".join(blocks).strip()


def _clean_glm_ocr_text(raw: str) -> str:
    """Strip layout/markdown noise that GLM-OCR appends to the recognized text.

    GLM-OCR tends to emit a clean transcription, then echo it inside a
    markdown code fence, then leave a long tail of empty ``````` lines.
    This helper removes HTML tags, HTML comments, empty markdown fences,
    and empty single-tag lines, deduplicates repeated blocks, then
    collapses excess blank lines.
    """
    if not raw:
        return raw
    cleaned = _HTML_COMMENT_RE.sub("", raw)
    cleaned = _LAYOUT_TAG_RE.sub("", cleaned)
    cleaned = _EMPTY_FENCE_LINE_RE.sub("", cleaned)
    cleaned = _EMPTY_TAG_LINE_RE.sub("", cleaned)
    cleaned = _dedupe_repeated_blocks(cleaned)
    cleaned = _MULTI_BLANK_RE.sub("\n\n", cleaned)
    return cleaned.strip()


class GLMOCRProvider(BaseOCRProvider):
    """GLM-OCR parser running against a local Ollama server.

    Configuration
    -------------
    - ``ENABLE_GLM_OCR=true`` — enables the engine for routing.
    - ``OLLAMA_BASE_URL``     — Ollama HTTP endpoint (default
      ``http://localhost:11434``).
    - ``OLLAMA_GLM_OCR_MODEL`` — model tag (default ``glm-ocr:latest``).
    - ``GLM_OCR_TIMEOUT_SECONDS`` — per-call HTTP timeout (default 120s).
    """

    feature_flag_name = "enable_glm_ocr"
    supported_file_types = frozenset({"png", "jpeg", "tiff"})

    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_glm_ocr_model
        self._timeout = settings.glm_ocr_timeout_seconds

    @property
    def provider_id(self) -> str:
        return "glmocr"

    @property
    def display_name(self) -> str:
        return "GLM-OCR (local Ollama)"

    def is_available(self) -> bool:
        """Probe the local Ollama endpoint and confirm the model is pulled.

        We do a short ``/api/tags`` GET and check the model list. Anything
        else (connection error, missing model) counts as unavailable so
        the auto-router can fall through to the next engine.
        """
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self._base_url}/api/tags")
            if resp.status_code != 200:
                return False
            payload = resp.json()
            models = {m.get("name") for m in payload.get("models", [])}
            return self._model in models
        except (httpx.HTTPError, ValueError) as exc:
            logger.debug("GLM-OCR availability check failed: %s", exc)
            return False

    async def extract_text(self, file_path: Path) -> OCRResult:
        if not file_path.exists():
            raise OCRProviderError(self.provider_id, f"File not found: {file_path.name}")

        try:
            image_bytes = file_path.read_bytes()
        except OSError as exc:
            raise OCRProviderError(self.provider_id, str(exc)) from exc

        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        # GLM-OCR's "Text Recognition:" prefix reliably triggers the OCR head.
        # We append an instruction that suppresses the trailing HTML/markdown
        # scaffolding the model likes to emit when no guidance is provided.
        prompt = (
            "Text Recognition: Read the text exactly as it appears in the image. "
            "Output only the recognized text. Do not add HTML, markdown fences, "
            "tables, tags, or commentary. Stop after the last visible line."
        )

        payload = {
            "model": self._model,
            "prompt": prompt,
            "images": [image_b64],
            "stream": False,
            "options": {"temperature": 0},
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/generate", json=payload)
        except httpx.HTTPError as exc:
            raise OCRProviderError(
                self.provider_id,
                f"Could not reach local Ollama at {self._base_url}: {exc}",
            ) from exc

        if resp.status_code != 200:
            raise OCRProviderError(
                self.provider_id,
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}",
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise OCRProviderError(
                self.provider_id, f"Ollama returned non-JSON response: {exc}"
            ) from exc

        raw = data.get("response", "") or ""
        cleaned = _clean_glm_ocr_text(raw)

        if not cleaned:
            raise OCRProviderError(
                self.provider_id,
                "GLM-OCR returned no text. The model may not be loaded locally.",
            )

        page_results = [
            OCRPageResult(
                page_index=0,
                text=cleaned,
            )
        ]

        eval_count = data.get("eval_count")
        prompt_eval_count = data.get("prompt_eval_count")

        return OCRResult(
            text=cleaned,
            pages=[cleaned],
            provider=self.provider_id,
            page_results=page_results,
            raw={
                "engine": "glm-ocr",
                "runtime": f"Ollama ({self._base_url})",
                "model": self._model,
                "eval_count": eval_count,
                "prompt_eval_count": prompt_eval_count,
            },
        )
