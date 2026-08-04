"""Read-only document inspection views built from durable page checkpoints."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from app.models.db_models import ParseJob
from app.models.enums import PageStatus
from app.services.parsing.agentic_contracts import PageDiagnostics
from app.services.parsing.contracts import DocumentLayout, PageLayout, Region
from app.services.parsing.ingest import render_page
from app.services.parsing.markdown import MarkdownRenderer
from app.services.parsing.storage import ObjectStore

TEXT_BEARING_TYPES = {
    "title",
    "heading",
    "text",
    "list",
    "table",
    "formula",
    "header",
    "footer",
    "page_number",
    "code",
    "quote",
    "form_field",
}


def load_page_layout(job: ParseJob, page_number: int, store: ObjectStore) -> PageLayout:
    checkpoint = next((item for item in job.pages if item.page_number == page_number), None)
    expected = f"jobs/{job.id}/checkpoints/p{page_number:04d}/layout.json"
    if checkpoint is None or checkpoint.layout_path != expected:
        raise KeyError("page layout is unavailable")
    return PageLayout.model_validate_json(store.read(expected))


def load_page_diagnostics(
    job: ParseJob, page_number: int, store: ObjectStore
) -> PageDiagnostics | None:
    checkpoint = next((item for item in job.pages if item.page_number == page_number), None)
    expected = f"jobs/{job.id}/checkpoints/p{page_number:04d}/diagnostics.json"
    if checkpoint is None or checkpoint.diagnostics_path != expected:
        return None
    return PageDiagnostics.model_validate_json(store.read(expected))


def completed_layouts(job: ParseJob, store: ObjectStore) -> list[PageLayout]:
    layouts: list[PageLayout] = []
    for checkpoint in job.pages:
        if checkpoint.status != PageStatus.COMPLETED or not checkpoint.layout_path:
            continue
        try:
            layouts.append(load_page_layout(job, checkpoint.page_number, store))
        except (KeyError, OSError, ValueError):
            continue
    return layouts


def render_source_page(job: ParseJob, page_number: int, dpi: int, store: ObjectStore) -> bytes:
    source = store.read(job.source_path)
    return render_page(source, job.original_filename, page_number, dpi).image_png


def _candidate_id(region_id: str, index: int, source: str, model: str | None, output: str) -> str:
    digest = hashlib.sha256(f"{source}\0{model or ''}\0{output}".encode()).hexdigest()[:12]
    return f"{region_id}-a{index + 1}-{digest}"


def _region_markdown(region: Region) -> str:
    page = PageLayout(page_number=1, width=1, height=1, regions=[region.model_copy(deep=True)])
    return MarkdownRenderer().render(DocumentLayout(pages=[page]), "keep_all").clean.strip()


def page_inspection(job: ParseJob, page_number: int, store: ObjectStore) -> dict[str, Any]:
    layout = load_page_layout(job, page_number, store)
    diagnostics = load_page_diagnostics(job, page_number, store)
    decisions = (
        {item.observation.region_id: item for item in diagnostics.region_decisions}
        if diagnostics
        else {}
    )
    regions: list[dict[str, Any]] = []
    for index, region in enumerate(layout.regions):
        region_id = region.id or f"p{page_number:04d}-r{index + 1:04d}"
        decision = decisions.get(region_id)
        candidates: list[dict[str, Any]] = []
        if decision:
            for attempt_index, attempt in enumerate(decision.attempts):
                candidates.append(
                    {
                        "id": _candidate_id(
                            region_id,
                            attempt_index,
                            attempt.source,
                            attempt.model,
                            attempt.output,
                        ),
                        "attempt": attempt.attempt,
                        "source": attempt.source,
                        "model": attempt.model,
                        "output": attempt.output,
                        "selected": attempt_index == decision.selected_attempt_index,
                        "verdict": attempt.verdict,
                        "reason": attempt.reason,
                        "confidence": region.confidence,
                        "latency_ms": attempt.latency_ms,
                        "warnings": attempt.warnings,
                    }
                )
        elif region.recognition_candidates:
            for candidate_index, candidate in enumerate(region.recognition_candidates):
                candidates.append(
                    {
                        "id": _candidate_id(
                            region_id,
                            candidate_index,
                            candidate.source,
                            candidate.model,
                            candidate.content,
                        ),
                        "attempt": candidate_index + 1,
                        "source": candidate.source,
                        "model": candidate.model,
                        "output": candidate.content,
                        "selected": candidate.selected,
                        "verdict": "pass" if candidate.selected else "warn",
                        "reason": "Recognition candidate retained for audit",
                        "confidence": candidate.confidence,
                        "latency_ms": candidate.latency_ms,
                        "warnings": [],
                    }
                )
        regions.append(
            {
                "id": region_id,
                "type": region.type,
                "bbox": region.bbox.model_dump(mode="json"),
                "order": region.order if region.order is not None else index,
                "confidence": region.confidence,
                "source": region.source,
                "source_label": region.source_label,
                "content": region.content,
                "markdown": _region_markdown(region),
                "parent_id": region.parent_id,
                "warnings": region.warnings,
                "quality_status": decision.final_status if decision else None,
                "candidates": candidates,
                "visual_verification": (
                    decision.visual_verification.model_dump(mode="json")
                    if decision and decision.visual_verification
                    else None
                ),
            }
        )
    settings = job.settings or {}
    return {
        "page_number": page_number,
        "width": layout.width,
        "height": layout.height,
        "coordinate_unit": layout.coordinate_unit,
        "image_url": f"/api/parse-jobs/{job.id}/pages/{page_number}/image?dpi=200",
        "quality_status": diagnostics.quality_status if diagnostics else None,
        "quality_score": (
            diagnostics.quality_score.model_dump(mode="json")
            if diagnostics and diagnostics.quality_score
            else None
        ),
        "reviewer": {
            "provider": settings.get("review_provider"),
            "model": job.review_model_name or settings.get("review_model"),
            "enabled": settings.get("cloud_mode", "off") != "off",
        },
        "warnings": list(
            dict.fromkeys([*layout.warnings, *(diagnostics.warnings if diagnostics else [])])
        ),
        "regions": regions,
    }


def document_tree(job: ParseJob, store: ObjectStore, query: str = "") -> list[dict[str, Any]]:
    layouts = completed_layouts(job, store)
    if not layouts:
        return []
    needle = query.casefold().strip()
    nodes: list[dict[str, Any]] = []
    heading_stack: list[tuple[int, str, str]] = []
    ordinal = 0
    for page in layouts:
        for region_index, region in enumerate(page.regions, start=1):
            ordinal += 1
            region_id = region.id or f"p{page.page_number:04d}-r{region_index:04d}"
            level = region.heading_level or (1 if region.type == "title" else 2)
            if region.type in {"title", "heading"}:
                while heading_stack and heading_stack[-1][0] >= level:
                    heading_stack.pop()
                parent_id = heading_stack[-1][1] if heading_stack else None
                heading_path = [item[2] for item in heading_stack] + [region.content.strip()]
                heading_stack.append((level, region_id, region.content.strip()))
            else:
                parent_id = region.parent_id or (heading_stack[-1][1] if heading_stack else None)
                heading_path = [item[2] for item in heading_stack]
            haystack = " ".join([region_id, region.type, region.content, *heading_path]).casefold()
            if needle and needle not in haystack:
                continue
            nodes.append(
                {
                    "id": region_id,
                    "page": page.page_number,
                    "order": ordinal,
                    "type": region.type,
                    "content": region.content,
                    "summary": re.sub(r"\s+", " ", region.content).strip()[:180],
                    "parent_id": parent_id,
                    "heading_path": heading_path,
                    "bbox": region.bbox.model_dump(mode="json"),
                    "source": region.source,
                    "confidence": region.confidence,
                    "warnings": region.warnings,
                }
            )
    return nodes


def quality_report(job: ParseJob, store: ObjectStore) -> dict[str, Any]:
    layouts = completed_layouts(job, store)
    text_regions = [
        region for page in layouts for region in page.regions if region.type in TEXT_BEARING_TYPES
    ]
    covered = sum(bool(region.content.strip()) for region in text_regions)
    disagreements: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    warnings: list[str] = []
    for page in layouts:
        warnings.extend(page.warnings)
        diagnostics = load_page_diagnostics(job, page.page_number, store)
        decision_by_id = (
            {item.observation.region_id: item for item in diagnostics.region_decisions}
            if diagnostics
            else {}
        )
        for region in page.regions:
            source_counts[region.source] += 1
            warnings.extend(region.warnings)
            normalized = {
                re.sub(r"\s+", " ", item.content).strip().casefold()
                for item in region.recognition_candidates
                if item.content.strip()
            }
            if len(normalized) > 1:
                disagreements.append(
                    {
                        "page": page.page_number,
                        "region_id": region.id,
                        "candidate_count": len(normalized),
                    }
                )
            decision = decision_by_id.get(region.id or "")
            if decision and decision.final_status != "pass":
                unresolved.append(
                    {
                        "page": page.page_number,
                        "region_id": region.id,
                        "status": decision.final_status,
                        "type": region.type,
                    }
                )
        if diagnostics:
            warnings.extend(diagnostics.warnings)
    tables = [region for page in layouts for region in page.regions if region.type == "table"]
    valid_tables = sum(
        bool(region.content.strip())
        and (
            bool(region.table_cells) or "|" in region.content or "<table" in region.content.lower()
        )
        for region in tables
    )
    selected_complete = bool(job.pages) and all(
        page.status == PageStatus.COMPLETED for page in job.pages
    )
    verified = (
        selected_complete
        and not unresolved
        and not any(
            case.status == "open" and case.item_kind == "region" for case in job.review_cases
        )
    )
    return {
        "schema_version": "paperplane-quality/v1",
        "job_id": job.id,
        "processed_pages": len(layouts),
        "ocr_coverage": {
            "covered_regions": covered,
            "total_regions": len(text_regions),
            "ratio": covered / len(text_regions) if text_regions else 1.0,
        },
        "disagreements": disagreements,
        "unresolved_regions": unresolved,
        "source_counts": dict(sorted(source_counts.items())),
        "table_integrity": {
            "passing_tables": valid_tables,
            "total_tables": len(tables),
            "ratio": valid_tables / len(tables) if tables else 1.0,
            "evaluated_accuracy": None,
        },
        "warnings": list(dict.fromkeys(warnings)),
        "verified_export_ready": verified,
    }
