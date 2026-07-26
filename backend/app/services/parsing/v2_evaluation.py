"""Deterministic evaluation for grounded V2 document artifacts."""

from __future__ import annotations

from difflib import SequenceMatcher

from pydantic import BaseModel

from app.services.parsing.contracts import BoundingBox
from app.services.parsing.v2_contracts import DocumentResult, GroundedChunk


class GroundedEvaluationReport(BaseModel):
    schema_version: str = "paperplane-evaluation/v2"
    metrics: dict[str, float]
    matched_chunks: int
    predicted_chunks: int
    labeled_chunks: int
    unmatched_predicted: list[str]
    unmatched_labels: list[str]


def evaluate_grounded_document(
    predicted: DocumentResult, labels: DocumentResult
) -> GroundedEvaluationReport:
    expected = {chunk.id: chunk for chunk in labels.chunks}
    actual = {chunk.id: chunk for chunk in predicted.chunks}
    matched_ids = sorted(actual.keys() & expected.keys())
    text = [_similarity(actual[item].text, expected[item].text) for item in matched_ids]
    boxes = [
        _iou(actual[item].grounding[0].box, expected[item].grounding[0].box)
        for item in matched_ids
        if actual[item].grounding and expected[item].grounding
    ]
    types = [float(actual[item].type == expected[item].type) for item in matched_ids]
    checkboxes = [
        float(_checkbox_state(actual[item]) == _checkbox_state(expected[item]))
        for item in matched_ids
        if actual[item].type == "checkbox" or expected[item].type == "checkbox"
    ]
    citation_coverage = (
        sum(bool(chunk.grounding) for chunk in predicted.chunks) / len(predicted.chunks)
        if predicted.chunks
        else 1.0
    )
    precision = len(matched_ids) / len(actual) if actual else float(not expected)
    recall = len(matched_ids) / len(expected) if expected else float(not actual)
    metrics = {
        "chunk_precision": precision,
        "chunk_recall": recall,
        "text_similarity": _mean(text),
        "mean_bbox_iou": _mean(boxes),
        "region_type_accuracy": _mean(types),
        "citation_coverage": citation_coverage,
        "checkbox_accuracy": _mean(checkboxes, empty=1.0),
    }
    metrics["macro_score"] = _mean(list(metrics.values()))
    return GroundedEvaluationReport(
        metrics=metrics,
        matched_chunks=len(matched_ids),
        predicted_chunks=len(actual),
        labeled_chunks=len(expected),
        unmatched_predicted=sorted(actual.keys() - expected.keys()),
        unmatched_labels=sorted(expected.keys() - actual.keys()),
    )


def _similarity(first: str, second: str) -> float:
    def normalize(value: str) -> str:
        return " ".join(value.casefold().split())

    return SequenceMatcher(None, normalize(first), normalize(second), autojunk=False).ratio()


def _iou(first: BoundingBox, second: BoundingBox) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = width * height
    first_area = (first.right - first.left) * (first.bottom - first.top)
    second_area = (second.right - second.left) * (second.bottom - second.top)
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _checkbox_state(chunk: GroundedChunk) -> str:
    text = chunk.text.lstrip()
    return "checked" if text.startswith(("☒", "☑", "[x]", "[X]")) else "unchecked"


def _mean(values: list[float], *, empty: float = 0.0) -> float:
    return sum(values) / len(values) if values else empty
