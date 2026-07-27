"""Deterministic v3 evaluation for page-oriented grounded artifacts."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher

from pydantic import BaseModel

from app.services.parsing.contracts import BoundingBox
from app.services.parsing.v2_contracts import DocumentItem, DocumentResult


class GroundedEvaluationReport(BaseModel):
    schema_version: str = "paperplane-evaluation/v3"
    metrics: dict[str, float]
    per_page: dict[int, dict[str, float]]
    matched_items: int
    predicted_items: int
    labeled_items: int
    unmatched_predicted: list[str]
    unmatched_labels: list[str]


def evaluate_grounded_document(
    predicted: DocumentResult, labels: DocumentResult
) -> GroundedEvaluationReport:
    actual = {item.id: item for page in predicted.pages for item in page.items}
    expected = {item.id: item for page in labels.pages for item in page.items}
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
    form_values = [
        float(_normalize(actual[item].text) == _normalize(expected[item].text))
        for item in matched_ids
        if actual[item].type == "form_field" or expected[item].type == "form_field"
    ]
    figure_labels = {item for item, value in expected.items() if value.type in {"figure", "chart"}}
    figure_matches = figure_labels & actual.keys()
    citation_coverage = (
        sum(bool(item.grounding) for item in actual.values()) / len(actual) if actual else 1.0
    )
    precision = len(matched_ids) / len(actual) if actual else float(not expected)
    recall = len(matched_ids) / len(expected) if expected else float(not actual)
    per_page: dict[int, dict[str, float]] = {}
    for page_number in range(1, predicted.source.page_count + 1):
        predicted_page = predicted.pages[page_number - 1]
        labeled_page = labels.pages[page_number - 1]
        per_page[page_number] = _token_metrics(
            _prose(predicted_page.items), _prose(labeled_page.items)
        )
    token_precision = _mean([item["token_precision"] for item in per_page.values()], empty=1.0)
    token_recall = _mean([item["token_recall"] for item in per_page.values()], empty=1.0)
    metrics = {
        "item_precision": precision,
        "item_recall": recall,
        "token_precision": token_precision,
        "token_recall": token_recall,
        "token_f1": _f1(token_precision, token_recall),
        "text_similarity": _mean(text, empty=1.0),
        "mean_bbox_iou": _mean(boxes, empty=1.0),
        "region_type_accuracy": _mean(types, empty=1.0),
        "citation_coverage": citation_coverage,
        "checkbox_accuracy": _mean(checkboxes, empty=1.0),
        "form_value_accuracy": _mean(form_values, empty=1.0),
        "list_order_accuracy": float(_list_order(predicted) == _list_order(labels)),
        "figure_coverage": len(figure_matches) / len(figure_labels) if figure_labels else 1.0,
        "duplicate_sibling_score": float(not _has_duplicate_siblings(predicted)),
    }
    metrics["macro_score"] = _mean(list(metrics.values()))
    return GroundedEvaluationReport(
        metrics=metrics,
        per_page=per_page,
        matched_items=len(matched_ids),
        predicted_items=len(actual),
        labeled_items=len(expected),
        unmatched_predicted=sorted(actual.keys() - expected.keys()),
        unmatched_labels=sorted(expected.keys() - actual.keys()),
    )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _similarity(first: str, second: str) -> float:
    return SequenceMatcher(None, _normalize(first), _normalize(second), autojunk=False).ratio()


def _tokens(value: str) -> Counter[str]:
    return Counter(re.findall(r"\w+", value.casefold()))


def _token_metrics(predicted: str, expected: str) -> dict[str, float]:
    actual_tokens, expected_tokens = _tokens(predicted), _tokens(expected)
    matched = sum((actual_tokens & expected_tokens).values())
    precision = (
        matched / sum(actual_tokens.values()) if actual_tokens else float(not expected_tokens)
    )
    recall = (
        matched / sum(expected_tokens.values()) if expected_tokens else float(not actual_tokens)
    )
    return {
        "token_precision": precision,
        "token_recall": recall,
        "token_f1": _f1(precision, recall),
    }


def _prose(items: list[DocumentItem]) -> str:
    return " ".join(item.text for item in items if item.type not in {"figure", "chart"})


def _list_order(document: DocumentResult) -> list[str]:
    return [item.id for page in document.pages for item in page.items if item.type == "list"]


def _has_duplicate_siblings(document: DocumentResult) -> bool:
    for page in document.pages:
        siblings = [item for item in page.items if item.parent_id is None and item.text.strip()]
        for index, first in enumerate(siblings):
            first_text = _normalize(first.text)
            for second in siblings[index + 1 :]:
                second_text = _normalize(second.text)
                if first_text in second_text or second_text in first_text:
                    return True
    return False


def _iou(first: BoundingBox, second: BoundingBox) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = width * height
    first_area = (first.right - first.left) * (first.bottom - first.top)
    second_area = (second.right - second.left) * (second.bottom - second.top)
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def _checkbox_state(item: DocumentItem) -> str:
    text = item.text.lstrip()
    return "checked" if text.startswith(("☒", "☑", "[x]", "[X]")) else "unchecked"


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def _mean(values: list[float], *, empty: float = 0.0) -> float:
    return sum(values) / len(values) if values else empty
