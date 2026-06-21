"""Eval subsystem — quality metrics for document extraction.

This is the v0.4.0 eval layer: golden-set driven, field-F1 + ECE
calibration metrics, per-field isotonic confidence calibration,
and the eval report builder used by ``just eval`` and the G-Eval
judge in ``app.services.eval.judge``.
"""

from app.services.eval.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationMap,
    FieldCalibrator,
    apply_calibration,
    fit_calibrator,
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
    "CalibrationMap",
    "EvalReport",
    "FieldCalibrator",
    "FieldComparison",
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
    "reliability_diagram_text",
    "render_reliability_diagram",
    "schema_conformance_rate",
]
