"""Versioned, profile-aware quality policies for agentic parsing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QualityOverrides(BaseModel):
    min_region_confidence: float | None = Field(default=None, ge=0, le=1)
    min_overall: float | None = Field(default=None, ge=0, le=1)
    min_extraction_accuracy: float | None = Field(default=None, ge=0, le=1)
    min_structural_fidelity: float | None = Field(default=None, ge=0, le=1)
    min_completeness: float | None = Field(default=None, ge=0, le=1)
    min_markdown_consistency: float | None = Field(default=None, ge=0, le=1)
    min_table_integrity: float | None = Field(default=None, ge=0, le=1)
    min_citation_coverage: float | None = Field(default=None, ge=0, le=1)
    max_repairs: int | None = Field(default=None, ge=0, le=2)


class QualityThresholds(BaseModel):
    min_region_confidence: float
    min_overall: float
    min_extraction_accuracy: float
    min_structural_fidelity: float
    min_completeness: float
    min_markdown_consistency: float
    min_table_integrity: float
    min_citation_coverage: float
    max_repairs: int


class QualityPolicy(BaseModel):
    schema_version: Literal["paperplane-quality-policy/v1"] = "paperplane-quality-policy/v1"
    policy_version: Literal["1"] = "1"
    processing_mode: Literal["local_only", "hybrid", "maximum_accuracy"]
    profile: str
    thresholds: QualityThresholds
    hard_gates: list[str] = Field(
        default_factory=lambda: [
            "valid_bbox",
            "semantic_content_present",
            "table_structure_valid",
            "grounded_citations_valid",
            "schema_valid",
        ]
    )


_DEFAULTS: dict[str, dict[str, float | int]] = {
    "local_only": {
        "min_region_confidence": 0.75,
        "min_overall": 0.80,
        "min_extraction_accuracy": 0.80,
        "min_structural_fidelity": 0.80,
        "min_completeness": 0.90,
        "min_markdown_consistency": 0.85,
        "min_table_integrity": 0.85,
        "min_citation_coverage": 1.0,
        "max_repairs": 2,
    },
    "hybrid": {
        "min_region_confidence": 0.82,
        "min_overall": 0.88,
        "min_extraction_accuracy": 0.88,
        "min_structural_fidelity": 0.88,
        "min_completeness": 0.93,
        "min_markdown_consistency": 0.90,
        "min_table_integrity": 0.92,
        "min_citation_coverage": 1.0,
        "max_repairs": 2,
    },
    "maximum_accuracy": {
        "min_region_confidence": 0.90,
        "min_overall": 0.93,
        "min_extraction_accuracy": 0.93,
        "min_structural_fidelity": 0.93,
        "min_completeness": 0.97,
        "min_markdown_consistency": 0.95,
        "min_table_integrity": 0.96,
        "min_citation_coverage": 1.0,
        "max_repairs": 2,
    },
}


def resolve_quality_policy(
    processing_mode: str, profile: str, overrides: QualityOverrides | dict[str, Any] | None = None
) -> QualityPolicy:
    values = dict(_DEFAULTS[processing_mode])
    if profile in {"technical_document", "scientific_paper"}:
        _raise(values, "min_structural_fidelity", "min_markdown_consistency", "min_table_integrity")
    elif profile in {"invoice", "insurance_claim", "healthcare_form"}:
        _raise(values, "min_extraction_accuracy", "min_completeness", "min_table_integrity")
    elif profile == "general_scanned":
        _raise(values, "min_region_confidence", "min_extraction_accuracy", "min_completeness")
    values.update(QualityOverrides.model_validate(overrides or {}).model_dump(exclude_none=True))
    return QualityPolicy(
        processing_mode=processing_mode,
        profile=profile,
        thresholds=QualityThresholds.model_validate(values),
    )


def _raise(values: dict[str, float | int], *names: str) -> None:
    for name in names:
        values[name] = min(1.0, float(values[name]) + 0.03)
