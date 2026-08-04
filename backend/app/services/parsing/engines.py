"""Vision-provider zone repair engine for the local parsing pipeline."""

from __future__ import annotations

import asyncio
import difflib
import io
import re
from pathlib import Path
from typing import Literal, cast

from PIL import Image

from app.services.parsing.contracts import RecognitionCandidate, Region
from app.services.parsing.parser import LayoutEngine, LayoutParser
from app.services.parsing.vision_providers import VisionProviderRegistry

PromptKind = Literal["text", "table", "chart", "formula", "figure"]


def _crop(image_path: Path, zone: Region) -> bytes:
    with Image.open(image_path) as image:
        width, height = image.size
        crop = image.crop(
            (
                int(zone.bbox.left * width),
                int(zone.bbox.top * height),
                max(1, int(zone.bbox.right * width)),
                max(1, int(zone.bbox.bottom * height)),
            )
        )
        output = io.BytesIO()
        crop.convert("RGB").save(output, "PNG")
        return output.getvalue()


class VisionZoneEngine:
    """Repair a low-confidence region using a cloud vision provider."""

    def __init__(self, providers: VisionProviderRegistry) -> None:
        self.providers = providers

    async def process(
        self,
        image_path: Path,
        zone: Region,
        device: str = "auto",
        model: str | None = None,
        provider: str = "openai",
    ) -> Region:
        del device
        if not model:
            raise ValueError("A repair model must be selected")
        image = await asyncio.to_thread(_crop, image_path, zone)
        kind: PromptKind = (
            cast(PromptKind, zone.type)
            if zone.type in {"table", "chart", "formula", "figure"}
            else "text"
        )
        prompt = {
            "text": "Transcribe this crop as exact Markdown. Return only Markdown.",
            "table": "Transcribe this table as complete Markdown. Return only the table.",
            "chart": "Describe this chart faithfully, including labels, axes, and values, as Markdown.",
            "formula": "Transcribe this formula as LaTeX. Return only LaTeX.",
            "figure": "Describe this figure faithfully as concise Markdown.",
        }[kind]
        result = await self.providers.generate(provider, model, image, prompt)
        content, source = result.text, "cloud_vlm"
        input_tokens, output_tokens, latency_ms = (
            result.input_tokens,
            result.output_tokens,
            result.latency_ms,
        )
        candidates = [
            candidate.model_copy(update={"selected": False})
            for candidate in zone.recognition_candidates
        ]
        if not candidates and zone.content.strip():
            candidates.append(
                RecognitionCandidate(
                    source=zone.source,
                    content=zone.content,
                    confidence=zone.confidence,
                    selected=False,
                )
            )
        candidates.append(
            RecognitionCandidate(
                source=source,
                content=content,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=latency_ms,
                selected=True,
            )
        )
        warnings = [
            warning
            for warning in zone.warnings
            if not warning.startswith("recognition_disagreement")
        ]
        if zone.content.strip() and _candidate_similarity(zone.content, content) < 0.6:
            warnings.append("recognition_disagreement")
        return zone.model_copy(
            update={
                "content": content,
                "source": source,
                "recognition_candidates": candidates,
                "warnings": warnings,
            }
        )


def _candidate_similarity(first: str, second: str) -> float:
    def normalize(value: str) -> str:
        return re.sub(r"[^\w]+", " ", value.casefold()).strip()

    return difflib.SequenceMatcher(None, normalize(first), normalize(second)).ratio()


def build_default_parser(
    providers: VisionProviderRegistry, layout_engine: LayoutEngine | None = None
) -> LayoutParser:
    repair = VisionZoneEngine(providers)
    return LayoutParser(layout_engine=layout_engine, text_engine=repair, table_engine=repair)
