"""Build durable page diagnostics from final parser state."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.parsing.agentic_contracts import (
    AttemptRecord,
    ExpertKind,
    PageDiagnostics,
    PagePlan,
    PlanningMode,
    ProcessingStage,
    ProcessingStrategy,
    QualityScore,
    QualityStatus,
    RegionDecision,
    RegionObservation,
    RegionPlan,
)
from app.services.parsing.contracts import PageLayout, Region


def _strategy(region: Region) -> ProcessingStrategy:
    if region.source == "native":
        return ProcessingStrategy.NATIVE
    if region.source == "fallback":
        return ProcessingStrategy.FALLBACK
    if region.type in {"table", "chart", "figure", "formula"}:
        return ProcessingStrategy.SPECIALIST
    return ProcessingStrategy.OCR


def _expert(region: Region) -> ExpertKind:
    return {
        "table": ExpertKind.TABLE,
        "chart": ExpertKind.CHART,
        "figure": ExpertKind.FIGURE,
        "formula": ExpertKind.FORMULA,
    }.get(region.type, ExpertKind.TEXT)


def plan_page(page_number: int, regions: list[Region], confidence_threshold: float) -> PagePlan:
    plans = []
    for region in regions:
        risks = list(region.warnings)
        if not region.content.strip():
            risks.append("empty_zone")
        if region.confidence is not None and region.confidence < confidence_threshold:
            risks.append("low_confidence")
        expert = _expert(region)
        plans.append(
            RegionPlan(
                region_id=region.id or "unknown",
                strategy=_strategy(region),
                expert=expert,
                difficulty=min(
                    1.0, 0.25 + (0.45 if expert != ExpertKind.TEXT else 0) + 0.1 * len(risks)
                ),
                rationale="Accept primary output when gates pass; otherwise use the specialist repair route",
                risk_flags=list(dict.fromkeys(risks)),
                prompt_variant="repair" if risks else "primary",
            )
        )
    return PagePlan(
        page_number=page_number,
        source="deterministic",
        regions=plans,
        rationale="Profile-aware plan created before recognition and verification",
    )


def _fallback_score(page: PageLayout) -> QualityScore:
    considered = [
        region for region in page.regions if region.type not in {"header", "footer", "page_number"}
    ]
    complete = sum(bool(region.content.strip()) for region in considered) / max(len(considered), 1)
    warnings = [warning for region in considered for warning in region.warnings]
    confidence_values = [
        region.confidence for region in considered if region.confidence is not None
    ]
    accuracy = sum(confidence_values) / len(confidence_values) if confidence_values else complete
    structure = 1.0 if not any("overlap" in warning for warning in warnings) else 0.5
    markdown = 1.0 if not any("broken_table" in warning for warning in warnings) else 0.5
    dimensions = (accuracy, structure, complete, markdown)
    return QualityScore(
        extraction_accuracy=dimensions[0],
        structural_fidelity=dimensions[1],
        completeness=dimensions[2],
        markdown_consistency=dimensions[3],
        overall=sum(dimensions) / 4,
        reasons=warnings,
    )


def build_page_diagnostics(
    page: PageLayout,
    review: dict[str, Any] | None,
    *,
    repair_count: int,
    warnings: list[str],
    visual_verifications: dict[str, Any] | None = None,
    planned: PagePlan | None = None,
) -> PageDiagnostics:
    score = QualityScore.model_validate(review["score"]) if review else _fallback_score(page)
    reviewed = {item["region_id"]: item for item in (review or {}).get("regions", [])}
    plans: list[RegionPlan] = []
    decisions: list[RegionDecision] = []
    for region in page.regions:
        region_id = region.id or "unknown"
        item = reviewed.get(region_id, {})
        risk_flags = list(item.get("risk_flags", region.warnings))
        strategy = _strategy(region)
        expert = _expert(region)
        selected_candidates = region.recognition_candidates
        selected_candidate_index = next(
            (index for index, candidate in enumerate(selected_candidates) if candidate.selected),
            max(0, len(selected_candidates) - 1),
        )
        glm_candidate_indexes = [
            index
            for index, candidate in enumerate(selected_candidates)
            if candidate.source == "glm_ocr"
        ]
        blind_retry = (
            len(glm_candidate_indexes) > 1 and selected_candidate_index == glm_candidate_indexes[-1]
        )
        prompt_variant = "blind_retry" if blind_retry else "repair" if repair_count else "primary"
        planned_region = next(
            (
                value
                for value in (planned.regions if planned else [])
                if value.region_id == region_id
            ),
            None,
        )
        plan = planned_region or RegionPlan(
            region_id=region_id,
            strategy=strategy,
            expert=expert,
            difficulty=min(
                1.0, 0.25 + (0.45 if expert != ExpertKind.TEXT else 0) + 0.1 * len(risk_flags)
            ),
            rationale="Route region according to content type and available native text",
            risk_flags=risk_flags,
            prompt_variant=prompt_variant,
        )
        plans.append(plan)
        verdict = QualityStatus(item.get("verdict", "warn" if region.warnings else "pass"))
        attempts = [
            AttemptRecord(
                attempt=index + 1,
                strategy=strategy,
                expert=expert,
                prompt_id=f"{expert.value}-recognition",
                prompt_version="1",
                prompt_variant=(
                    "blind_retry"
                    if candidate.source == "glm_ocr"
                    and index == glm_candidate_indexes[-1]
                    and len(glm_candidate_indexes) > 1
                    else "primary"
                ),
                source=candidate.source,
                model=candidate.model,
                output=candidate.content,
                score=score,
                verdict=verdict if index == selected_candidate_index else QualityStatus.WARN,
                reason=(
                    str(item.get("reason", "Deterministic parser checks completed"))
                    if index == selected_candidate_index
                    else "Recognition candidate retained for audit"
                ),
                repair_hint=(
                    item.get("repair_hint") if index == selected_candidate_index else None
                ),
                warnings=list(region.warnings),
                latency_ms=candidate.latency_ms,
                eval_count=candidate.output_tokens,
                prompt_eval_count=candidate.input_tokens,
            )
            for index, candidate in enumerate(selected_candidates)
        ]
        if not attempts:
            attempts = [
                AttemptRecord(
                    attempt=1,
                    strategy=strategy,
                    expert=expert,
                    prompt_id=f"{expert.value}-recognition",
                    prompt_version="1",
                    prompt_variant=plan.prompt_variant,
                    source=region.source,
                    output=region.content,
                    score=score,
                    verdict=verdict,
                    reason=str(item.get("reason", "Deterministic parser checks completed")),
                    repair_hint=item.get("repair_hint"),
                    warnings=list(region.warnings),
                    latency_ms=float((review or {}).get("latency_ms", 0)),
                    eval_count=(review or {}).get("eval_count"),
                    prompt_eval_count=(review or {}).get("prompt_eval_count"),
                )
            ]
            selected_candidate_index = 0
        observation = RegionObservation(
            region_id=region_id,
            region_type=region.type,
            bbox=region.bbox,
            content=region.content,
            native_text=region.content if region.source == "native" else "",
            native_healthy=region.source == "native" and bool(region.content.strip()),
            confidence=region.confidence,
            risk_flags=risk_flags,
        )
        decisions.append(
            RegionDecision(
                observation=observation,
                plan=plan,
                attempts=attempts,
                selected_attempt_index=selected_candidate_index,
                final_status=verdict,
                visual_verification=(visual_verifications or {}).get(region_id),
            )
        )

    statuses = [decision.final_status for decision in decisions]
    status = (
        QualityStatus.FAIL
        if QualityStatus.FAIL in statuses
        else QualityStatus.WARN
        if QualityStatus.WARN in statuses or warnings
        else QualityStatus.PASS
    )
    fingerprint = hashlib.sha256(
        json.dumps(page.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return PageDiagnostics(
        planning_mode=PlanningMode.PAGE_CENTRIC,
        stage=ProcessingStage.COMPLETED,
        page_number=page.page_number,
        plan=planned
        or PagePlan(
            page_number=page.page_number,
            source="model" if review else "deterministic",
            regions=plans,
            rationale="Plan derived from final layout and visual alignment review",
            warnings=list(warnings),
        ),
        region_decisions=decisions,
        quality_score=score,
        quality_status=status,
        repair_count=repair_count,
        warnings=list(warnings),
        fingerprint=fingerprint,
    )
