"""Structured visual alignment review through a local Ollama VLM."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Literal

import httpx
from pydantic import BaseModel, Field

from app.services.parsing.agentic_contracts import QualityScore
from app.services.parsing.vision_providers import ProviderError, VisionProviderRegistry


class ReviewUnavailable(RuntimeError):
    """Raised when the local reviewer cannot return a valid result."""


class RegionReview(BaseModel):
    region_id: str
    verdict: Literal["pass", "warn", "fail"]
    reason: str
    repair_hint: str | None = None
    risk_flags: list[str] = Field(default_factory=list)


class _ReviewPayload(BaseModel):
    extraction_accuracy: float = Field(ge=0, le=1)
    structural_fidelity: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    markdown_consistency: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    regions: list[RegionReview] = Field(default_factory=list)


@dataclass(frozen=True)
class ReviewResult:
    score: QualityScore
    regions: list[RegionReview]
    eval_count: int | None = None
    prompt_eval_count: int | None = None
    latency_ms: float = 0


def _review_prompt(
    markdown: str,
    allowed_region_ids: list[str],
    candidate_context: dict[str, list[str]] | None,
    coordinate_manifest: dict[str, dict[str, object]] | None,
    *,
    json_only: bool,
) -> str:
    output = (
        " Return only JSON with extraction_accuracy, structural_fidelity, completeness, "
        "markdown_consistency (all 0..1), reasons, and regions. Each region must contain "
        "region_id, verdict (pass|warn|fail), reason, optional repair_hint, and risk_flags."
        if json_only
        else ""
    )
    candidates = ""
    if candidate_context:
        candidates = "\n\nLocal OCR candidates:\n" + json.dumps(
            candidate_context, ensure_ascii=False
        )
    coordinates = ""
    if coordinate_manifest:
        coordinates = "\n\nNormalized coordinate manifest:\n" + json.dumps(
            coordinate_manifest, ensure_ascii=False
        )
    return (
        "Compare the extracted text against the exact labeled visual coordinates in this "
        "annotated page image. Score fidelity, identify only real mismatches, reference only "
        "supplied region IDs, never propose replacement document text, "
        f"and do not repeat document text.{output}\n\n"
        f"Allowed region IDs: {', '.join(allowed_region_ids)}\n\nMarkdown:\n{markdown}"
        f"{candidates}{coordinates}"
    )


def _result(
    parsed: _ReviewPayload,
    allowed_region_ids: list[str],
    *,
    eval_count: int | None = None,
    prompt_eval_count: int | None = None,
    latency_ms: float = 0,
) -> ReviewResult:
    dimensions = (
        parsed.extraction_accuracy,
        parsed.structural_fidelity,
        parsed.completeness,
        parsed.markdown_consistency,
    )
    return ReviewResult(
        score=QualityScore(
            extraction_accuracy=dimensions[0],
            structural_fidelity=dimensions[1],
            completeness=dimensions[2],
            markdown_consistency=dimensions[3],
            overall=sum(dimensions) / len(dimensions),
            reasons=parsed.reasons,
        ),
        regions=[
            region for region in parsed.regions if region.region_id in set(allowed_region_ids)
        ],
        eval_count=eval_count,
        prompt_eval_count=prompt_eval_count,
        latency_ms=latency_ms,
    )


class OllamaReviewer:
    """Compare a rendered page against its Markdown without exposing cloud data."""

    prompt_id = "page-alignment-review"
    prompt_version = "1"

    def __init__(self, client: httpx.AsyncClient, model: str) -> None:
        self.client = client
        self.model = model

    async def review(
        self,
        image_png: bytes,
        markdown: str,
        allowed_region_ids: list[str],
        candidate_context: dict[str, list[str]] | None = None,
        coordinate_manifest: dict[str, dict[str, object]] | None = None,
    ) -> ReviewResult:
        prompt = _review_prompt(
            markdown,
            allowed_region_ids,
            candidate_context,
            coordinate_manifest,
            json_only=False,
        )
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64.b64encode(image_png).decode("ascii")],
                }
            ],
            "format": _ReviewPayload.model_json_schema(),
            "options": {"temperature": 0},
        }
        try:
            response = await self.client.post("/api/chat", json=payload)
            response.raise_for_status()
            envelope = response.json()
            content = envelope.get("message", {}).get("content", "")
            parsed = _ReviewPayload.model_validate(json.loads(content))
        except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ReviewUnavailable(f"Visual review failed: {type(exc).__name__}") from exc

        return _result(
            parsed,
            allowed_region_ids,
            eval_count=envelope.get("eval_count"),
            prompt_eval_count=envelope.get("prompt_eval_count"),
            latency_ms=float(envelope.get("total_duration", 0)) / 1_000_000,
        )


class ProviderReviewer:
    """Compare a page and Markdown through a configured cloud vision provider."""

    prompt_id = "page-alignment-review"
    prompt_version = "1"

    def __init__(self, registry: VisionProviderRegistry, provider: str, model: str) -> None:
        self.registry = registry
        self.provider = provider
        self.model = model

    async def review(
        self,
        image_png: bytes,
        markdown: str,
        allowed_region_ids: list[str],
        candidate_context: dict[str, list[str]] | None = None,
        coordinate_manifest: dict[str, dict[str, object]] | None = None,
    ) -> ReviewResult:
        prompt = _review_prompt(
            markdown,
            allowed_region_ids,
            candidate_context,
            coordinate_manifest,
            json_only=True,
        )
        try:
            generation = await self.registry.generate(self.provider, self.model, image_png, prompt)
            content = generation.text.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0]
            parsed = _ReviewPayload.model_validate(json.loads(content))
        except (ProviderError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ReviewUnavailable(f"Visual review failed: {type(exc).__name__}") from exc
        return _result(
            parsed,
            allowed_region_ids,
            eval_count=generation.output_tokens,
            prompt_eval_count=generation.input_tokens,
        )
