"""Ollama discovery and structured vision adapter."""

from __future__ import annotations

import asyncio
import base64
import html
import json
import time
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from paperplane.ollama_ocr import (
    LayoutDetector,
    OcrProfile,
    chunk_type_for_label,
    clean_ocr_output,
    crop_region,
    get_layout_detector,
    profile_for_family,
)
from paperplane.openai_document import OpenAIUsage, StructuredGeneration

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"


@dataclass(frozen=True, slots=True)
class OllamaModel:
    name: str
    capabilities: tuple[str, ...]
    family: str | None = None

    @property
    def vision_capable(self) -> bool:
        return "vision" in self.capabilities


class OllamaRequestError(RuntimeError):
    pass


class OllamaDocumentAdapter:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        base_url: str = DEFAULT_OLLAMA_BASE_URL,
        layout_detector: LayoutDetector | None = None,
    ) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")
        self.layout_detector = layout_detector
        self._families: dict[str, str | None] = {}

    async def list_models(self) -> list[OllamaModel]:
        try:
            response = await self.http.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            names = [str(item["name"]) for item in response.json().get("models", [])]
            models: list[OllamaModel] = []
            for name in names:
                detail = await self.http.post(f"{self.base_url}/api/show", json={"model": name})
                detail.raise_for_status()
                body = detail.json()
                capabilities = tuple(str(item) for item in body.get("capabilities", []))
                family = str(body.get("details", {}).get("family", "")) or None
                self._families[name] = family
                models.append(OllamaModel(name=name, capabilities=capabilities, family=family))
            return models
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise OllamaRequestError(
                "Ollama is unavailable or returned an invalid model list"
            ) from exc

    async def generate_structured(
        self,
        *,
        model: str,
        image: bytes | None,
        instructions: str,
        context: str | None = None,
        schema_name: str,
        schema: dict[str, Any],
        reasoning_effort: Literal["none", "low", "medium", "high"],
        detail: Literal["low", "high", "original"],
        prompt_cache_key: str,
    ) -> StructuredGeneration:
        del schema_name, reasoning_effort, detail, prompt_cache_key
        family = await self._model_family(model)
        profile = profile_for_family(family)
        if image is not None and profile is not None and "chunks" in schema.get("properties", {}):
            return await self._generate_ocr_page(model, image, profile)
        content = instructions
        if context:
            content += f"\n\nPrior/local document context:\n{context}"
        message: dict[str, Any] = {"role": "user", "content": content}
        if image is not None:
            message["images"] = [base64.b64encode(image).decode("ascii")]
        started = time.perf_counter()
        try:
            response = await self.http.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [message],
                    "format": schema,
                    "stream": False,
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
            body = response.json()
            value = json.loads(body["message"]["content"])
            if not isinstance(value, dict):
                raise TypeError("structured response is not an object")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OllamaRequestError("Ollama document request failed") from exc
        return StructuredGeneration(
            response_id=None,
            value=value,
            usage=OpenAIUsage(
                input_tokens=int(body.get("prompt_eval_count", 0)),
                output_tokens=int(body.get("eval_count", 0)),
            ),
            latency_ms=(time.perf_counter() - started) * 1000,
        )

    async def _model_family(self, model: str) -> str | None:
        if model in self._families:
            return self._families[model]
        try:
            response = await self.http.post(f"{self.base_url}/api/show", json={"model": model})
            response.raise_for_status()
            family = str(response.json().get("details", {}).get("family", "")) or None
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            raise OllamaRequestError("Ollama could not inspect the selected model") from exc
        self._families[model] = family
        return family

    async def _generate_ocr_page(
        self, model: str, image: bytes, profile: OcrProfile
    ) -> StructuredGeneration:
        detector = self.layout_detector or get_layout_detector()
        started = time.perf_counter()
        try:
            regions = await asyncio.to_thread(detector.detect, image)
        except Exception as exc:
            raise OllamaRequestError("Ollama layout detection failed") from exc
        if not regions:
            raise OllamaRequestError("Ollama layout detection found no document regions")

        chunks: list[dict[str, Any]] = []
        input_tokens = 0
        output_tokens = 0
        for region in regions:
            prompt = profile.prompt_for(region.label)
            chunk_type = chunk_type_for_label(region.label)
            region_area = (region.right - region.left) * (region.bottom - region.top)
            max_tokens = 512 if chunk_type == "table" else 256 if region_area > 0.03 else 128
            encoded = base64.b64encode(crop_region(image, region)).decode("ascii")
            try:
                response = await self.http.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
                        "stream": False,
                        "options": {
                            "temperature": 0,
                            "num_ctx": 4096,
                            "num_predict": max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                body = response.json()
                content = clean_ocr_output(str(body["message"]["content"]))
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise OllamaRequestError(
                    f"Ollama OCR failed for {region.label} region {len(chunks) + 1}"
                ) from exc
            input_tokens += int(body.get("prompt_eval_count", 0) or 0)
            output_tokens += int(body.get("eval_count", 0) or 0)
            if not content and chunk_type not in {"figure", "chart"}:
                continue
            if chunk_type in {"figure", "chart"}:
                description = (
                    f"<description>{html.escape(content)}</description>" if content else ""
                )
                markdown = f'<figure type="{chunk_type}">{description}</figure>'
            else:
                markdown = content
            chunks.append(
                {
                    "type": chunk_type,
                    "text": content,
                    "markdown": markdown,
                    "box": {
                        "left": region.left,
                        "top": region.top,
                        "right": region.right,
                        "bottom": region.bottom,
                    },
                    "parent_order": None,
                    "atomic_lines": [],
                    "row": None,
                    "col": None,
                    "rowspan": None,
                    "colspan": None,
                }
            )
        if not chunks:
            raise OllamaRequestError("Ollama OCR returned no document content")
        return StructuredGeneration(
            value={"chunks": chunks},
            usage=OpenAIUsage(input_tokens=input_tokens, output_tokens=output_tokens),
            latency_ms=(time.perf_counter() - started) * 1000,
            presegmented=True,
        )


class ChainedStructuredAdapter:
    """Run Ollama first, then let a cloud adapter validate/refine its structured draft."""

    def __init__(self, local: OllamaDocumentAdapter, cloud: Any, *, cloud_model: str) -> None:
        self.local = local
        self.cloud = cloud
        self.cloud_model = cloud_model

    async def generate_structured(self, **kwargs: Any) -> StructuredGeneration:
        local = await self.local.generate_structured(**kwargs)
        cloud_kwargs = dict(kwargs)
        cloud_kwargs["model"] = self.cloud_model
        local_context = json.dumps(local.value, ensure_ascii=False, separators=(",", ":"))
        existing = cloud_kwargs.get("context")
        cloud_kwargs["context"] = (
            f"{existing}\n\nOllama draft:\n{local_context}"
            if existing
            else f"Ollama draft:\n{local_context}"
        )
        refined = await self.cloud.generate_structured(**cloud_kwargs)
        return StructuredGeneration(
            response_id=refined.response_id,
            value=refined.value,
            usage=OpenAIUsage(
                input_tokens=local.usage.input_tokens + refined.usage.input_tokens,
                output_tokens=local.usage.output_tokens + refined.usage.output_tokens,
                cached_input_tokens=refined.usage.cached_input_tokens,
                cache_write_tokens=refined.usage.cache_write_tokens,
            ),
            latency_ms=local.latency_ms + refined.latency_ms,
        )


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "ChainedStructuredAdapter",
    "OllamaDocumentAdapter",
    "OllamaModel",
    "OllamaRequestError",
]
