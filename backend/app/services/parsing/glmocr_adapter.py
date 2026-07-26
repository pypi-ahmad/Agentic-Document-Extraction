"""Small direct client for the local Ollama GLM-OCR runtime."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.config import settings

PromptKind = Literal["text", "table", "chart", "formula", "figure"]
PROMPTS: dict[PromptKind, str] = {
    "text": "Transcribe this crop as exact Markdown. Return only Markdown.",
    "table": "Transcribe this table as a complete GitHub Markdown table. Return only the table.",
    "chart": "Describe this chart faithfully, including labels, axes, and values, as Markdown.",
    "formula": "Transcribe this formula as LaTeX.",
    "figure": "Describe this figure faithfully as concise Markdown.",
}


class GLMOCRUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class OllamaReadiness:
    ready: bool
    model: str
    digest: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class RecognitionResult:
    text: str
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    latency_ms: float = 0


class GLMOCRAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None, model: str | None = None) -> None:
        self._client = client
        self.base_url = settings.ollama_base_url.rstrip("/")
        if not model:
            raise ValueError("An Ollama model must be selected")
        self.model = model

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return await self._client.request(method, path, **kwargs)
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=settings.glm_ocr_timeout_seconds
        ) as client:
            return await client.request(method, path, **kwargs)

    async def readiness(self) -> OllamaReadiness:
        try:
            response = await self._request("GET", "/api/tags")
            response.raise_for_status()
            envelope = response.json()
            models = envelope.get("models", []) if isinstance(envelope, dict) else []
            for model in models:
                if isinstance(model, dict) and (
                    model.get("name") == self.model or model.get("model") == self.model
                ):
                    return OllamaReadiness(True, self.model, model.get("digest"))
            return OllamaReadiness(False, self.model, error="model_not_found")
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            return OllamaReadiness(False, self.model, error=type(exc).__name__)

    async def recognize(self, image_bytes: bytes, kind: PromptKind) -> RecognitionResult:
        prompt = PROMPTS[kind]
        payload = {
            "model": self.model,
            "prompt": prompt,
            "images": [base64.b64encode(image_bytes).decode("ascii")],
            "stream": False,
            "options": {"temperature": 0},
        }
        started = time.perf_counter()
        try:
            response = await self._request("POST", "/api/generate", json=payload)
            response.raise_for_status()
            envelope = response.json()
            text = envelope.get("response", "") if isinstance(envelope, dict) else ""
            if not isinstance(text, str) or not text.strip():
                raise ValueError("empty OCR response")
            return RecognitionResult(
                text.strip(),
                envelope.get("eval_count"),
                envelope.get("prompt_eval_count"),
                (time.perf_counter() - started) * 1000,
            )
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GLMOCRUnavailable(f"Local GLM-OCR request failed: {type(exc).__name__}") from exc

    async def unload(self) -> None:
        try:
            response = await self._request(
                "POST",
                "/api/generate",
                json={"model": self.model, "prompt": "", "keep_alive": 0},
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise GLMOCRUnavailable(
                f"Could not unload local model: {type(exc).__name__}"
            ) from exc
