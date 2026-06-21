"""Eval subsystem — quality metrics for document extraction.

This is the v0.4.0 eval layer: golden-set driven, field-F1 + ECE
calibration metrics, and the eval report builder used by ``just
eval`` and the G-Eval judge in ``app.services.eval.judge``.
"""

from app.services.eval.metrics import (
    EvalReport,
    FieldComparison,
    anls,
    auroc,
    brier,
    build_report,
    compare_field,
    coverage_at_target_accuracy,
    ece,
    field_f1,
    reliability_diagram_text,
    render_reliability_diagram,
    schema_conformance_rate,
)

__all__ = [
    "EvalReport",
    "FieldComparison",
    "anls",
    "auroc",
    "brier",
    "build_report",
    "compare_field",
    "coverage_at_target_accuracy",
    "ece",
    "field_f1",
    "reliability_diagram_text",
    "render_reliability_diagram",
    "schema_conformance_rate",
]
