"""Document-wide LangGraph for layout-aware Markdown parsing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.models.schemas import ParseSettings
from app.services.parsing.agentic_contracts import (
    VerificationMethod,
    VisualVerification,
)
from app.services.parsing.artifacts import build_verification_overlay, crop_region
from app.services.parsing.contracts import Region
from app.services.parsing.diagnostics import plan_page
from app.services.parsing.parser import LayoutParser
from app.services.parsing.quality_policy import resolve_quality_policy
from app.services.parsing.review import OllamaReviewer, ProviderReviewer, ReviewUnavailable
from app.services.parsing.verification import verify_region_coordinates


class ParserState(TypedDict, total=False):
    job_id: str
    source_path: str
    work_dir: str
    settings: dict[str, Any]
    page_images: list[str]
    native_words: dict[int, list[dict[str, Any]]]
    zones: dict[int, list[dict[str, Any]]]
    markdown: str
    grounded_markdown: str
    context: dict[str, Any]
    needs_repair: bool
    repair_issues: list[str]
    blind_retry_pending: list[str]
    blind_retry_completed: list[str]
    visual_verifications: dict[int, dict[str, dict[str, Any]]]
    repair_count: int
    max_repairs: int
    warnings: list[str]
    reviews: dict[int, dict[str, Any]]
    layout: dict[str, Any]
    figure_crops: dict[str, str]
    status: str
    page_numbers: list[int]
    page_plans: dict[int, dict[str, Any]]


def reflection_router(state: ParserState) -> str:
    if state.get("needs_repair", False) and state.get("repair_count", 0) < state.get(
        "max_repairs", 2
    ):
        return "local_recognition"
    return "finalize"


def build_parser_graph(
    parser: LayoutParser,
    checkpointer: Any | None = None,
    reviewer_factory: Callable[[str, str], OllamaReviewer | ProviderReviewer] | None = None,
    reviewer: OllamaReviewer | None = None,
) -> Any:
    async def ingest_and_render(state: ParserState) -> dict[str, Any]:
        settings = ParseSettings.model_validate(state.get("settings", {}))
        images, native = await parser.ingest(
            Path(state["source_path"]),
            Path(state["work_dir"]),
            settings,
            state.get("page_numbers"),
        )
        return {"page_images": images, "native_words": native, "status": "ingesting"}

    async def visual_segmentation(state: ParserState) -> dict[str, Any]:
        settings = ParseSettings.model_validate(state.get("settings", {}))
        parsed = await parser.segment_document(
            job_id=state["job_id"],
            image_paths=[Path(image) for image in state["page_images"]],
            native_words=state.get("native_words", {}),
            input_mode=settings.input_mode,
            work_dir=Path(state["work_dir"]),
            layout_device=settings.layout_device,
        )
        zones = {
            page: [zone.model_dump(mode="json") for zone in values]
            for page, values in parsed.items()
        }
        return {"zones": zones, "status": "segmenting"}

    async def local_recognition(state: ParserState) -> dict[str, Any]:
        processed: dict[int, list[dict[str, Any]]] = {}
        settings = ParseSettings.model_validate(state.get("settings", {}))
        images = {_page_number(path): Path(path) for path in state["page_images"]}
        incoming_issues = set(state.get("repair_issues", []))
        issues = set(incoming_issues)
        blind_retry_pending = set(state.get("blind_retry_pending", []))
        primary_scan_pass = False
        native_words = state.get("native_words", {})
        scan_pages = {
            int(page)
            for page in state["zones"]
            if settings.input_mode == "scanned"
            or (settings.input_mode == "mixed" and not native_words.get(int(page)))
        }
        if not issues and state.get("repair_count", 0) == 0 and scan_pages and settings.ocr_model:
            primary_scan_pass = True
            issues = {
                f"p{int(page)}:{Region.model_validate(raw).id}:scanned_recheck"
                for page, raw_zones in state["zones"].items()
                if int(page) in scan_pages
                for raw in raw_zones
            }
        if not issues:
            return {
                "zones": state["zones"],
                "repair_count": state.get("repair_count", 0),
                "status": "processing",
            }
        semaphore = asyncio.Semaphore(settings.region_concurrency)
        for page, raw_zones in state["zones"].items():
            page_number = int(page)

            async def process(
                raw: dict[str, Any], current_page: int = page_number
            ) -> dict[str, Any]:
                zone = Region.model_validate(raw)
                targeted = any(f"p{current_page}:{zone.id}:" in issue for issue in issues)
                region_key = f"p{current_page}:{zone.id}"
                if (
                    zone.type == "figure"
                    and not settings.describe_figures
                    and region_key not in blind_retry_pending
                ):
                    result = zone.model_copy(update={"content": zone.content or "Figure"})
                else:
                    async with semaphore:
                        result = (
                            await parser.process_zone(
                                images[current_page],
                                zone,
                                settings.layout_device,
                                settings.ocr_model,
                                settings.ocr_provider,
                            )
                            if targeted
                            else zone
                        )
                return result.model_dump(mode="json")

            values = list(await asyncio.gather(*(process(raw) for raw in raw_zones)))
            processed[page_number] = values
        return {
            "zones": processed,
            "repair_count": state.get("repair_count", 0)
            + (1 if incoming_issues and not primary_scan_pass else 0),
            "blind_retry_completed": sorted(
                set(state.get("blind_retry_completed", [])) | blind_retry_pending
            ),
            "blind_retry_pending": [],
            "status": "processing",
        }

    async def agent_planning(state: ParserState) -> dict[str, Any]:
        settings = ParseSettings.model_validate(state.get("settings", {}))
        policy = resolve_quality_policy(
            settings.processing_mode, settings.document_profile, settings.quality_overrides
        )
        plans = {
            int(page): plan_page(
                int(page),
                [Region.model_validate(raw) for raw in raw_zones],
                policy.thresholds.min_region_confidence,
            ).model_dump(mode="json")
            for page, raw_zones in state["zones"].items()
        }
        return {"page_plans": plans, "status": "planning"}

    async def layout_stitching(state: ParserState) -> dict[str, Any]:
        pages = _regions(state)
        settings = ParseSettings.model_validate(state.get("settings", {}))
        images = {_page_number(path): Path(path) for path in state["page_images"]}
        figures_dir = Path(state["work_dir"]) / "figures"
        await asyncio.to_thread(figures_dir.mkdir, parents=True, exist_ok=True)
        figure_crops: dict[str, str] = {}
        warnings = list(state.get("warnings", []))
        visual_verifications: dict[int, dict[str, dict[str, Any]]] = {}
        for page, regions in pages.items():
            candidates = [region for region in regions if region.type in {"figure", "chart"}]
            if not candidates:
                continue
            image_png = await asyncio.to_thread(images[page].read_bytes)
            visual_verifications[page] = await asyncio.to_thread(
                verify_region_coordinates, image_png, regions
            )
            for region in candidates:
                if not region.id:
                    continue
                try:
                    data = await asyncio.to_thread(crop_region, image_png, region.bbox)
                    target = figures_dir / f"{region.id}.png"
                    await asyncio.to_thread(target.write_bytes, data)
                    region.crop_path = f"figures/{region.id}.png"
                    figure_crops[region.id] = str(target)
                except Exception as exc:
                    warnings.append(f"p{page}:{region.id}:figure_crop_failed:{type(exc).__name__}")
        document = parser.build_document_layout(pages)
        result = parser.stitch_layout(document, settings.marginalia_policy)
        return {
            "zones": {
                page: [region.model_dump(mode="json") for region in regions]
                for page, regions in pages.items()
            },
            "layout": document.model_dump(mode="json"),
            "figure_crops": figure_crops,
            "markdown": result.clean_markdown,
            "grounded_markdown": result.grounded_markdown,
            "context": {
                "schema_version": "1",
                "chunks": [chunk.model_dump(mode="json") for chunk in result.context_chunks],
            },
            "warnings": warnings,
            "visual_verifications": visual_verifications,
            "status": "stitching",
        }

    async def cloud_context_review(state: ParserState) -> dict[str, Any]:
        settings = ParseSettings.model_validate(state.get("settings", {}))
        policy = resolve_quality_policy(
            settings.processing_mode,
            settings.document_profile,
            settings.quality_overrides,
        )
        _, detected_issues = parser.reflect(
            _regions(state), policy.thresholds.min_region_confidence
        )
        soft_markers = ("low_confidence", "recognition_disagreement")
        issues = [issue for issue in detected_issues if not issue.endswith(soft_markers)]
        reviews: dict[int, dict[str, Any]] = {}
        blind_retry_pending: list[str] = []
        blind_retry_completed = set(state.get("blind_retry_completed", []))
        visual_verifications = {
            int(page): dict(values)
            for page, values in state.get("visual_verifications", {}).items()
        }
        warnings = list(state.get("warnings", []))
        selected_reviewer = (
            reviewer_factory(settings.review_provider, settings.review_model)
            if reviewer_factory
            and settings.review_model
            and settings.cloud_mode != "off"
            and not (
                settings.document_profile == "auto"
                and settings.review_provider != "ollama"
                and not settings.allow_sensitive_cloud
            )
            else reviewer
            if reviewer is not None and settings.cloud_mode != "off"
            else None
        )
        if selected_reviewer is not None:
            images = {_page_number(path): Path(path) for path in state["page_images"]}
            flagged_pages = {
                int(issue.split(":", 1)[0][1:])
                for issue in detected_issues
                if issue.startswith("p") and ":" in issue
            }
            flagged_pages.update(
                page
                for page, verifications in visual_verifications.items()
                if any(item.get("status") != "pass" for item in verifications.values())
            )
            pages_to_review = set(images) if settings.cloud_mode == "all_pages" else flagged_pages
            for page, regions in _regions(state).items():
                if page not in pages_to_review:
                    continue
                page_markdown = parser.stitch_document(
                    {page: regions}, settings.marginalia_policy
                ).clean_markdown
                region_ids = [region.id for region in regions if region.id]
                regions_by_id = {region.id: region for region in regions if region.id}
                candidate_context = {
                    region.id: [
                        f"{candidate.source}: {candidate.content[:1500]}"
                        for candidate in region.recognition_candidates[-2:]
                    ]
                    for region in regions
                    if region.id and region.recognition_candidates
                }
                coordinate_manifest: dict[str, dict[str, object]] = {
                    region.id: {
                        "bbox": [
                            region.bbox.left,
                            region.bbox.top,
                            region.bbox.right,
                            region.bbox.bottom,
                        ],
                        "type": region.type,
                        "text": region.content[:2000],
                    }
                    for region in regions
                    if region.id
                }
                try:
                    image_png = await asyncio.to_thread(images[page].read_bytes)
                    overlay_png = await asyncio.to_thread(
                        build_verification_overlay, image_png, regions
                    )
                    review = await selected_reviewer.review(
                        overlay_png,
                        page_markdown,
                        region_ids,
                        candidate_context,
                        coordinate_manifest,
                    )
                    statuses = [region.verdict for region in review.regions]
                    quality_status = (
                        "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"
                    )
                    reviews[page] = {
                        "score": review.score.model_dump(mode="json"),
                        "regions": [region.model_dump(mode="json") for region in review.regions],
                        "quality_status": quality_status,
                        "eval_count": review.eval_count,
                        "prompt_eval_count": review.prompt_eval_count,
                        "latency_ms": review.latency_ms,
                    }
                    score_values = review.score.model_dump(mode="json")
                    thresholds = policy.thresholds
                    score_gates = {
                        "overall": thresholds.min_overall,
                        "extraction_accuracy": thresholds.min_extraction_accuracy,
                        "structural_fidelity": thresholds.min_structural_fidelity,
                        "completeness": thresholds.min_completeness,
                        "markdown_consistency": thresholds.min_markdown_consistency,
                    }
                    failed_gates = [
                        name
                        for name, threshold in score_gates.items()
                        if float(score_values[name]) < threshold
                    ]
                    if failed_gates and all(status == "pass" for status in statuses):
                        issues.extend(
                            f"p{page}:{region_id}:quality_threshold:{','.join(failed_gates)}"
                            for region_id in region_ids
                        )
                    for region in review.regions:
                        existing = visual_verifications.get(page, {}).get(region.region_id)
                        verification = VisualVerification.model_validate(
                            existing
                            or {
                                "region_id": region.region_id,
                                "bbox": regions_by_id[region.region_id].bbox,
                                "status": "warn",
                            }
                        )
                        visual_verifications.setdefault(page, {})[region.region_id] = (
                            VisualVerification.model_validate(
                                {
                                    **verification.model_dump(mode="json"),
                                    "status": region.verdict,
                                    "methods": list(
                                        dict.fromkeys(
                                            [
                                                *verification.methods,
                                                VerificationMethod.CLOUD_VISUAL,
                                            ]
                                        )
                                    ),
                                    "reasons": [*verification.reasons, region.reason],
                                }
                            ).model_dump(mode="json")
                        )
                        if region.verdict == "fail":
                            region_key = f"p{page}:{region.region_id}"
                            if (
                                settings.blind_local_retry
                                and region_key not in blind_retry_completed
                            ):
                                issues.append(f"{region_key}:cloud_disagreement_blind_retry")
                                blind_retry_pending.append(region_key)
                            else:
                                warnings.append(f"{region_key}:cloud_disagreement_unresolved")
                        elif region.verdict == "warn":
                            warnings.append(f"p{page}:{region.region_id}:{region.reason}")
                except ReviewUnavailable as exc:
                    warnings.append(f"p{page}:visual_review_unavailable:{type(exc).__name__}")
        needs_repair = bool(issues)
        return {
            "needs_repair": needs_repair,
            "repair_issues": issues,
            "blind_retry_pending": blind_retry_pending,
            "blind_retry_completed": sorted(blind_retry_completed),
            "visual_verifications": visual_verifications,
            "repair_count": state.get("repair_count", 0),
            "reviews": reviews,
            "warnings": warnings,
            "status": "reflecting",
        }

    async def finalize(state: ParserState) -> dict[str, Any]:
        warnings = list(state.get("warnings", []))
        if state.get("needs_repair"):
            warnings.extend(state.get("repair_issues", []))
        return {
            "warnings": warnings,
            "status": "completed_with_warnings" if warnings else "completed",
        }

    graph = StateGraph(ParserState)
    for name, node in (
        ("ingest_and_render", ingest_and_render),
        ("visual_segmentation", visual_segmentation),
        ("agent_planning", agent_planning),
        ("local_recognition", local_recognition),
        ("layout_stitching", layout_stitching),
        ("cloud_context_review", cloud_context_review),
        ("finalize", finalize),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "ingest_and_render")
    graph.add_edge("ingest_and_render", "visual_segmentation")
    graph.add_edge("visual_segmentation", "agent_planning")
    graph.add_edge("agent_planning", "local_recognition")
    graph.add_edge("local_recognition", "layout_stitching")
    graph.add_edge("layout_stitching", "cloud_context_review")
    graph.add_conditional_edges(
        "cloud_context_review",
        reflection_router,
        {"local_recognition": "local_recognition", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


def _page_number(path: str) -> int:
    return int(Path(path).stem.rsplit("-", 1)[1])


def _regions(state: ParserState) -> dict[int, list[Region]]:
    return {
        int(page): [Region.model_validate(zone) for zone in zones]
        for page, zones in state["zones"].items()
    }
