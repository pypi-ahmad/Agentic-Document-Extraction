"""Deterministic comparison of parsed layouts against grounded labels."""

from __future__ import annotations

from difflib import SequenceMatcher
from itertools import combinations
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.services.parsing.contracts import BoundingBox, DocumentLayout, RegionType
from app.services.parsing.segmentation import DetectedSubDocument


class GoldRegion(BaseModel):
    id: str
    type: RegionType
    order: int = Field(ge=0)
    bbox: BoundingBox
    text: str
    heading_level: int | None = Field(default=None, ge=1, le=6)
    parent_id: str | None = None
    table_cells: list[list[str]] | list[dict[str, Any]] | None = None


class GoldPage(BaseModel):
    page: int = Field(ge=1)
    regions: list[GoldRegion]


class GoldSubDocument(BaseModel):
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    profile: str
    identifiers: dict[str, str] = Field(default_factory=dict)


class GroundTruthDocument(BaseModel):
    schema_version: Literal[
        "paperplane-ground-truth/v1",
        "paperplane-ground-truth/v2",
        "paperplane-ground-truth/v3",
    ]
    document_id: str = Field(min_length=1, max_length=200)
    source_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    markdown: str
    pages: list[GoldPage]
    subdocuments: list[GoldSubDocument] = Field(default_factory=list)
    schema_extractions: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_regions(self) -> GroundTruthDocument:
        ids = [region.id for page in self.pages for region in page.regions]
        if len(ids) != len(set(ids)):
            raise ValueError("gold region IDs must be unique")
        return self


class EvaluationReport(BaseModel):
    schema_version: Literal["paperplane-eval/v1"] = "paperplane-eval/v1"
    document_id: str
    metrics: dict[str, float]
    matched_regions: int
    predicted_regions: int
    gold_regions: int
    unmatched_predicted: list[str]
    unmatched_gold: list[str]


def evaluate_document(
    predicted_markdown: str,
    predicted_layout: DocumentLayout,
    gold: GroundTruthDocument,
    predicted_subdocuments: list[DetectedSubDocument] | None = None,
) -> EvaluationReport:
    predicted = [
        (page.page_number, index, region)
        for page in predicted_layout.pages
        for index, region in enumerate(page.regions)
    ]
    expected = [(page.page, region.order, region) for page in gold.pages for region in page.regions]
    matches = _align(predicted, expected)
    matched_pred = {p for p, _ in matches}
    matched_gold = {g for _, g in matches}
    precision = len(matches) / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = len(matches) / len(expected) if expected else (1.0 if not predicted else 0.0)
    region_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    bbox_scores = [_iou(predicted[p][2].bbox, expected[g][2].bbox) for p, g in matches]
    text_scores = [_similarity(predicted[p][2].content, expected[g][2].text) for p, g in matches]
    parents = _predicted_parents(predicted_layout)
    hierarchy = [
        float(parents.get(predicted[p][2].id or "") == expected[g][2].parent_id)
        for p, g in matches
        if predicted[p][2].type in {"title", "heading"}
        or expected[g][2].type in {"title", "heading"}
        or parents.get(predicted[p][2].id or "") is not None
        or expected[g][2].parent_id is not None
    ]
    order_score = _reading_order_accuracy(matches, predicted, expected)
    table_scores = [
        _table_f1(
            predicted[p][2].table_rows or [],
            _gold_cell_text(expected[g][2].table_cells or []),
        )
        for p, g in matches
        if predicted[p][2].type == "table" and expected[g][2].type == "table"
    ]
    table_bbox_scores = [
        _mean(
            [
                _iou(cell.bbox, BoundingBox.model_validate(gold_cell["bbox"]))
                for cell, gold_cell in zip(
                    predicted[p][2].table_cells,
                    _gold_cell_objects(expected[g][2].table_cells or []),
                    strict=False,
                )
                if "bbox" in gold_cell
            ],
            empty=1.0,
        )
        for p, g in matches
        if predicted[p][2].type == "table" and expected[g][2].type == "table"
    ]
    metrics = {
        "markdown_similarity": _similarity(predicted_markdown, gold.markdown),
        "region_precision": precision,
        "region_recall": recall,
        "region_f1": region_f1,
        "mean_bbox_iou": _mean(bbox_scores),
        "region_text_similarity": _mean(text_scores),
        "hierarchy_accuracy": _mean(hierarchy, empty=1.0),
        "reading_order_accuracy": order_score,
        "citation_coverage": sum(bool(region.id) for _, _, region in predicted) / len(predicted)
        if predicted
        else 1.0,
        "table_cell_f1": _mean(table_scores, empty=1.0),
        "table_cell_bbox_iou": _mean(table_bbox_scores, empty=1.0),
        "region_type_accuracy": _mean(
            [float(predicted[p][2].type == expected[g][2].type) for p, g in matches],
            empty=1.0,
        ),
    }
    if gold.subdocuments:
        metrics.update(_segmentation_metrics(predicted_subdocuments or [], gold.subdocuments))
    summary_keys = (
        "markdown_similarity",
        "region_f1",
        "mean_bbox_iou",
        "region_text_similarity",
        "hierarchy_accuracy",
        "reading_order_accuracy",
        "citation_coverage",
        "table_cell_f1",
        "table_cell_bbox_iou",
        "region_type_accuracy",
    )
    metrics["macro_score"] = _mean([metrics[key] for key in summary_keys])
    return EvaluationReport(
        document_id=gold.document_id,
        metrics=metrics,
        matched_regions=len(matches),
        predicted_regions=len(predicted),
        gold_regions=len(expected),
        unmatched_predicted=[
            predicted[index][2].id or f"predicted-{index}"
            for index in range(len(predicted))
            if index not in matched_pred
        ],
        unmatched_gold=[
            expected[index][2].id for index in range(len(expected)) if index not in matched_gold
        ],
    )


def _segmentation_metrics(
    predicted: list[DetectedSubDocument], expected: list[GoldSubDocument]
) -> dict[str, float]:
    predicted_boundaries = {item.end_page for item in predicted[:-1]}
    expected_boundaries = {item.end_page for item in expected[:-1]}
    matched = len(predicted_boundaries & expected_boundaries)
    precision = (
        matched / len(predicted_boundaries)
        if predicted_boundaries
        else float(not expected_boundaries)
    )
    recall = (
        matched / len(expected_boundaries)
        if expected_boundaries
        else float(not predicted_boundaries)
    )
    boundary_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    pages = sorted(
        {page for item in expected for page in range(item.start_page, item.end_page + 1)}
    )
    predicted_by_page = {
        page: item.profile
        for item in predicted
        for page in range(item.start_page, item.end_page + 1)
    }
    expected_by_page = {
        page: item.profile
        for item in expected
        for page in range(item.start_page, item.end_page + 1)
    }
    page_assignment = _mean(
        [float(predicted_by_page.get(page) == expected_by_page[page]) for page in pages],
        empty=1.0,
    )
    exact_instances = sum(
        any(
            candidate.start_page == item.start_page
            and candidate.end_page == item.end_page
            and candidate.profile == item.profile
            for candidate in predicted
        )
        for item in expected
    )
    return {
        "boundary_precision": precision,
        "boundary_recall": recall,
        "boundary_f1": boundary_f1,
        "subdocument_page_assignment_accuracy": page_assignment,
        "subdocument_instance_accuracy": exact_instances / len(expected) if expected else 1.0,
    }


def _align(predicted: list[tuple], expected: list[tuple]) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    unused_predicted = set(range(len(predicted)))
    unused_expected = set(range(len(expected)))
    expected_ids = {item[2].id: index for index, item in enumerate(expected)}
    for p_index, (_, _, region) in enumerate(predicted):
        g_index = expected_ids.get(region.id or "")
        if g_index is not None and g_index in unused_expected:
            matches.append((p_index, g_index))
            unused_predicted.discard(p_index)
            unused_expected.discard(g_index)
    candidates: list[tuple[float, int, int]] = []
    for p_index in unused_predicted:
        p_page, _, p_region = predicted[p_index]
        for g_index in unused_expected:
            g_page, _, g_region = expected[g_index]
            if p_page != g_page or p_region.type != g_region.type:
                continue
            iou = _iou(p_region.bbox, g_region.bbox)
            text = _similarity(p_region.content, g_region.text)
            if iou >= 0.5 or text >= 0.8:
                candidates.append((0.65 * iou + 0.35 * text, p_index, g_index))
    for _, p_index, g_index in sorted(candidates, key=lambda item: (-item[0], item[1], item[2])):
        if p_index in unused_predicted and g_index in unused_expected:
            matches.append((p_index, g_index))
            unused_predicted.remove(p_index)
            unused_expected.remove(g_index)
    return sorted(matches)


def _predicted_parents(layout: DocumentLayout) -> dict[str, str | None]:
    parents: dict[str, str | None] = {}
    stack: list[tuple[int, str]] = []
    for page in layout.pages:
        for region in page.regions:
            region_id = region.id or ""
            level = region.heading_level or (1 if region.type == "title" else 2)
            if region.type in {"title", "heading"}:
                while stack and stack[-1][0] >= level:
                    stack.pop()
                parents[region_id] = stack[-1][1] if stack else None
                stack.append((level, region_id))
            else:
                parents[region_id] = stack[-1][1] if stack else None
    return parents


def _reading_order_accuracy(
    matches: list[tuple[int, int]], predicted: list[tuple], expected: list[tuple]
) -> float:
    comparable = [(p, g) for p, g in matches]
    pairs = list(combinations(comparable, 2))
    if not pairs:
        return 1.0
    correct = 0
    for (p1, g1), (p2, g2) in pairs:
        predicted_order = (predicted[p1][0], predicted[p1][1]) < (
            predicted[p2][0],
            predicted[p2][1],
        )
        gold_order = (expected[g1][0], expected[g1][1]) < (expected[g2][0], expected[g2][1])
        correct += predicted_order == gold_order
    return correct / len(pairs)


def _table_f1(predicted: list[list[str]], expected: list[list[str]]) -> float:
    p = [" ".join(str(cell).split()).casefold() for row in predicted for cell in row]
    g = [" ".join(str(cell).split()).casefold() for row in expected for cell in row]
    if not p and not g:
        return 1.0
    matched = sum(a == b for a, b in zip(p, g, strict=False))
    precision = matched / len(p) if p else 0.0
    recall = matched / len(g) if g else 0.0
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _gold_cell_objects(cells: list[list[str]] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [cell for cell in cells if isinstance(cell, dict)]


def _gold_cell_text(cells: list[list[str]] | list[dict[str, Any]]) -> list[list[str]]:
    objects = _gold_cell_objects(cells)
    if objects:
        return [[str(cell.get("text", "")) for cell in objects]]
    return cells  # type: ignore[return-value]


def _similarity(first: str, second: str) -> float:
    def normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    return SequenceMatcher(None, normalize(first), normalize(second), autojunk=False).ratio()


def _iou(first: BoundingBox, second: BoundingBox) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = width * height
    union = (
        ((first.right - first.left) * (first.bottom - first.top))
        + ((second.right - second.left) * (second.bottom - second.top))
        - intersection
    )
    return intersection / union if union else 0.0


def _mean(values: list[float], *, empty: float = 0.0) -> float:
    return sum(values) / len(values) if values else empty
