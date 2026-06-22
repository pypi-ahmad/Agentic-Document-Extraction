"""Eval subsystem — quality metrics for document extraction.

This is the v0.4.0 eval layer: golden-set driven, field-F1 + ECE
calibration metrics, per-field isotonic confidence calibration,
the eval report builder, and the G-Eval LLM-as-judge.
"""

from app.services.eval.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationMap,
    FieldCalibrator,
    apply_calibration,
    fit_calibrator,
)
from app.services.eval.judge import (
    CRITERION_RUBRIC,
    DEFAULT_CRITERIA,
    G_EVAL_VERSION,
    CriterionScore,
    Judgment,
    is_below_threshold,
    judge_extraction,
    parse_judge_response,
    should_judge,
)
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
    "CALIBRATION_SCHEMA_VERSION",
    "CRITERION_RUBRIC",
    "DEFAULT_CRITERIA",
    "G_EVAL_VERSION",
    "CalibrationMap",
    "CriterionScore",
    "EvalReport",
    "FieldCalibrator",
    "FieldComparison",
    "Judgment",
    "anls",
    "apply_calibration",
    "auroc",
    "brier",
    "build_report",
    "compare_field",
    "coverage_at_target_accuracy",
    "ece",
    "field_f1",
    "fit_calibrator",
    "is_below_threshold",
    "judge_extraction",
    "parse_judge_response",
    "reliability_diagram_text",
    "render_reliability_diagram",
    "schema_conformance_rate",
    "should_judge",
]
