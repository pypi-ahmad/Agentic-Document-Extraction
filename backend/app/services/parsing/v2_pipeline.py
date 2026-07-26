"""Bounded evidence-first page processing for the OpenAI V2 pipeline."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.services.parsing.contracts import BoundingBox
from app.services.parsing.ingest import RenderedPage
from app.services.parsing.openai_document import OpenAIUsage, StructuredGeneration
from app.services.parsing.v2_contracts import (
    GroundedChunk,
    Grounding,
    GroundingMethod,
    ProcessingMode,
    VerificationStatus,
    mode_policy,
)
from app.services.parsing.v2_grounding import (
    align_text_to_native_words,
    map_crop_box_to_page,
    render_crop,
)

PAGE_DRAFT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "chunks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "title",
                            "heading",
                            "text",
                            "list",
                            "checkbox",
                            "table",
                            "table_cell",
                            "form_field",
                            "figure",
                            "chart",
                            "header",
                            "footer",
                        ],
                    },
                    "text": {"type": "string"},
                    "markdown": {"type": "string"},
                    "box": {
                        "type": "object",
                        "properties": {
                            "left": {"type": "number"},
                            "top": {"type": "number"},
                            "right": {"type": "number"},
                            "bottom": {"type": "number"},
                        },
                        "required": ["left", "top", "right", "bottom"],
                        "additionalProperties": False,
                    },
                    "parent_order": {"type": ["integer", "null"]},
                },
                "required": ["type", "text", "markdown", "box", "parent_order"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["chunks"],
    "additionalProperties": False,
}

CROP_VERIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "box": {
            "type": "object",
            "properties": {
                "left": {"type": "number"},
                "top": {"type": "number"},
                "right": {"type": "number"},
                "bottom": {"type": "number"},
            },
            "required": ["left", "top", "right", "bottom"],
            "additionalProperties": False,
        },
        "verdict": {"type": "string", "enum": ["verified", "unresolved"]},
        "reason": {"type": "string"},
    },
    "required": ["text", "box", "verdict", "reason"],
    "additionalProperties": False,
}


class StructuredAdapter(Protocol):
    async def generate_structured(self, **kwargs: Any) -> StructuredGeneration: ...


class PageResult(BaseModel):
    page_number: int
    chunks: list[GroundedChunk]
    markdown: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    model_usage: dict[str, OpenAIUsage] = Field(default_factory=dict)
    application_cache_hit: bool = False
    evidence_artifacts: dict[str, bytes] = Field(default_factory=dict, exclude=True)


def _same_text(left: str, right: str) -> bool:
    return " ".join(left.casefold().split()) == " ".join(right.casefold().split())


def _cache_key(prefix: str, source_sha256: str) -> str:
    shard = int(source_sha256[:8], 16) % 4
    return f"{prefix}:v2:shard-{shard}"


def _source_unit(filename: str) -> str:
    return "pdf_points" if Path(filename).suffix.lower() == ".pdf" else "image_pixels"


def _source_box(box: BoundingBox, page: RenderedPage) -> tuple[float, float, float, float]:
    return (
        box.left * page.width,
        box.top * page.height,
        box.right * page.width,
        box.bottom * page.height,
    )


class V2PageProcessor:
    def __init__(self, adapter: StructuredAdapter) -> None:
        self.adapter = adapter

    async def process_page(
        self,
        *,
        source: bytes,
        filename: str,
        source_sha256: str,
        page: RenderedPage,
        mode: ProcessingMode,
    ) -> PageResult:
        policy = mode_policy(mode)
        draft = await self.adapter.generate_structured(
            model="gpt-5.6-luna",
            image=page.image_png,
            instructions=(
                "Extract every visible document region in reading order. Return faithful text and "
                "Markdown, normalized top-left boxes, and parent order. Do not infer hidden values."
            ),
            schema_name="page_draft_v2",
            schema=PAGE_DRAFT_SCHEMA,
            reasoning_effort=policy.luna_reasoning_effort,
            detail="high",
            prompt_cache_key=_cache_key("page-draft", source_sha256),
        )
        chunks: list[GroundedChunk] = []
        evidence_artifacts: dict[str, bytes] = {}
        total_usage = draft.usage.model_copy()
        model_usage = {"gpt-5.6-luna": draft.usage.model_copy()}
        raw_chunks = draft.value.get("chunks", [])
        for order, raw in enumerate(raw_chunks, start=1):
            chunk_id = f"p{page.page_number:04d}-c{order:04d}"
            box = BoundingBox.model_validate(raw["box"])
            text = str(raw["text"])
            exact = align_text_to_native_words(text, page.native_words)
            if exact is not None:
                grounding = Grounding(
                    page=page.page_number,
                    box=exact,
                    method=GroundingMethod.TEXT_LAYER_EXACT,
                    source_box=_source_box(exact, page),
                    source_unit=_source_unit(filename),
                    evidence_artifact_id=f"page:{source_sha256}:{page.page_number}",
                )
                status = VerificationStatus.VERIFIED
                final_text = text
                final_markdown = str(raw["markdown"])
                warnings: list[str] = []
            elif policy.terra_scope == "none":
                grounding = Grounding(
                    page=page.page_number,
                    box=box,
                    method=GroundingMethod.VISION_REFINED,
                    source_box=_source_box(box, page),
                    source_unit=_source_unit(filename),
                    evidence_artifact_id=f"page:{source_sha256}:{page.page_number}",
                )
                status = VerificationStatus.CANDIDATE
                final_text = text
                final_markdown = str(raw["markdown"])
                warnings = ["single_model_candidate"]
            else:
                (
                    grounding,
                    status,
                    final_text,
                    final_markdown,
                    warnings,
                    usages,
                    evidence,
                ) = await self._verify_crop(
                    source=source,
                    filename=filename,
                    source_sha256=source_sha256,
                    page=page,
                    chunk_id=chunk_id,
                    chunk_type=str(raw["type"]),
                    candidate_text=text,
                    candidate_markdown=str(raw["markdown"]),
                    box=box,
                    crop_dpi=policy.crop_dpi,
                    reasoning_effort=policy.terra_reasoning_effort or "medium",
                    max_rounds=policy.max_repair_rounds,
                )
                for usage in usages:
                    total_usage.input_tokens += usage.input_tokens
                    total_usage.output_tokens += usage.output_tokens
                    total_usage.cached_input_tokens += usage.cached_input_tokens
                    total_usage.cache_write_tokens += usage.cache_write_tokens
                    terra_usage = model_usage.setdefault("gpt-5.6-terra", OpenAIUsage())
                    terra_usage.input_tokens += usage.input_tokens
                    terra_usage.output_tokens += usage.output_tokens
                    terra_usage.cached_input_tokens += usage.cached_input_tokens
                    terra_usage.cache_write_tokens += usage.cache_write_tokens
                evidence_artifacts.update(evidence)
            parent_order = raw.get("parent_order")
            parent_id = (
                f"p{page.page_number:04d}-c{int(parent_order):04d}"
                if isinstance(parent_order, int) and 0 < parent_order < order
                else None
            )
            chunks.append(
                GroundedChunk(
                    id=chunk_id,
                    page=page.page_number,
                    order=order,
                    type=raw["type"],
                    text=final_text,
                    markdown=final_markdown,
                    grounding=[grounding],
                    parent_id=parent_id,
                    verification_status=status,
                    source_model=(
                        "gpt-5.6-terra"
                        if status == VerificationStatus.VERIFIED and exact is None
                        else "gpt-5.6-luna"
                    ),
                    source_pass="crop_verification" if exact is None else "page_draft",
                    warnings=warnings,
                )
            )
        markdown = "\n\n".join(f'<a id="{chunk.id}"></a>\n\n{chunk.markdown}' for chunk in chunks)
        return PageResult(
            page_number=page.page_number,
            chunks=chunks,
            markdown=markdown,
            input_tokens=total_usage.input_tokens,
            output_tokens=total_usage.output_tokens,
            cached_input_tokens=total_usage.cached_input_tokens,
            cache_write_tokens=total_usage.cache_write_tokens,
            model_usage=model_usage,
            evidence_artifacts=evidence_artifacts,
        )

    async def _verify_crop(
        self,
        *,
        source: bytes,
        filename: str,
        source_sha256: str,
        page: RenderedPage,
        chunk_id: str,
        chunk_type: str,
        candidate_text: str,
        candidate_markdown: str,
        box: BoundingBox,
        crop_dpi: int,
        reasoning_effort: str,
        max_rounds: int,
    ):
        crop = render_crop(
            source, filename, page_number=page.page_number, box=box, dpi=crop_dpi, padding=0.05
        )
        evidence_hash = hashlib.sha256(crop.image_png).hexdigest()[:16]
        evidence_id = f"crop:{source_sha256}:{page.page_number}:{chunk_id}:{evidence_hash}"
        usages = []
        last_value: dict[str, Any] | None = None
        for attempt in range(max_rounds):
            instructions = (
                "Independently read this crop without guessing. Return only visible text, a box "
                "relative to the crop, and verified only when the crop is unambiguous."
                if attempt == 0
                else "Reinspect the crop. The prior readings disagreed; return unresolved unless "
                "the visible glyphs unambiguously determine the exact text."
            )
            result = await self.adapter.generate_structured(
                model="gpt-5.6-terra",
                image=crop.image_png,
                instructions=instructions,
                schema_name="crop_verification_v2",
                schema=CROP_VERIFICATION_SCHEMA,
                reasoning_effort=reasoning_effort,
                detail="original",
                prompt_cache_key=_cache_key("crop-verification", source_sha256),
            )
            usages.append(result.usage)
            last_value = result.value
            if result.value.get("verdict") == "verified" and _same_text(
                candidate_text, str(result.value.get("text", ""))
            ):
                relative = BoundingBox.model_validate(result.value["box"])
                refined = map_crop_box_to_page(crop.page_box, relative)
                grounding = Grounding(
                    page=page.page_number,
                    box=refined,
                    method=GroundingMethod.VISION_REFINED,
                    source_box=_source_box(refined, page),
                    source_unit=_source_unit(filename),
                    evidence_artifact_id=evidence_id,
                )
                return (
                    grounding,
                    VerificationStatus.VERIFIED,
                    candidate_text,
                    candidate_markdown,
                    [],
                    usages,
                    {evidence_id: crop.image_png},
                )
        relative = BoundingBox.model_validate((last_value or {}).get("box", box.model_dump()))
        refined = map_crop_box_to_page(crop.page_box, relative)
        grounding = Grounding(
            page=page.page_number,
            box=refined,
            method=GroundingMethod.VISION_REFINED,
            source_box=_source_box(refined, page),
            source_unit=_source_unit(filename),
            evidence_artifact_id=evidence_id,
        )
        return (
            grounding,
            VerificationStatus.UNRESOLVED,
            "",
            f"> [!WARNING]\n> Unresolved {chunk_type} on page {page.page_number}.",
            ["visual_disagreement"],
            usages,
            {evidence_id: crop.image_png},
        )
