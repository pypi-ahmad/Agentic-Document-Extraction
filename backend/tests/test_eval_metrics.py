"""Unit tests for the eval metrics module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.eval import (
    EvalReport,
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

# ── field_f1 ─────────────────────────────────────────────────────────


def test_field_f1_perfect() -> None:
    expected = {"a": "x", "b": 1, "c": True}
    predicted = {"a": "x", "b": 1, "c": True}
    p, r, f1, comps = field_f1(expected, predicted)
    assert p == 1.0
    assert r == 1.0
    assert f1 == 1.0
    assert all(c.correct for c in comps)


def test_field_f1_mixed() -> None:
    expected = {"a": "x", "b": 1}
    predicted = {"a": "x", "b": 2}
    p, r, f1, _ = field_f1(expected, predicted)
    assert p == 0.5
    assert r == 0.5
    assert f1 == 0.5


def test_field_f1_normalizes_case_and_whitespace() -> None:
    expected = {"a": "Hello World"}
    predicted = {"a": "  hello world  "}
    _, _, f1, comps = field_f1(expected, predicted)
    assert f1 == 1.0
    assert comps[0].correct


def test_field_f1_empty_is_zero() -> None:
    p, r, f1, _ = field_f1({}, {})
    assert (p, r, f1) == (0.0, 0.0, 0.0)


def test_compare_field_ignores_missing_values() -> None:
    cmp = compare_field("x", None, None)
    assert not cmp.correct  # both missing => not a true positive


def test_compare_field_handles_numbers() -> None:
    assert compare_field("x", 1.0, 1).correct
    assert compare_field("x", 1.5, 1.5).correct
    assert not compare_field("x", 1.5, 1.6).correct


# ── schema_conformance_rate ─────────────────────────────────────────


def test_schema_conformance_rate_basic() -> None:
    preds = [{"a": "x"}, {"a": 1}, {"b": "y"}]
    rate = schema_conformance_rate(preds, required_fields=("a",))
    assert rate == pytest.approx(2 / 3)


def test_schema_conformance_rate_handles_empty() -> None:
    assert schema_conformance_rate([]) == 0.0


# ── ANLS ────────────────────────────────────────────────────────────


def test_anls_exact_match() -> None:
    assert anls("hello world", "hello world") == 1.0


def test_anls_below_threshold_is_zero() -> None:
    assert anls("abc", "xyz") == 0.0


def test_anls_above_threshold_is_partial() -> None:
    score = anls("hello", "hello world")
    assert 0.0 < score < 1.0


def test_anls_empty_handling() -> None:
    assert anls("", "") == 1.0
    assert anls("x", "") == 0.0
    assert anls("", "x") == 0.0


# ── ECE / Brier / AUROC ────────────────────────────────────────────


def test_ece_perfectly_calibrated() -> None:
    """Two bins, each with perfect calibration: conf=0.1 -> all wrong, conf=0.9 -> all right.

    Bin [0, 0.1) has avg_conf=0.1, avg_acc=0.0, gap=0.1, weight=1/4.
    Bin [0.9, 1.0] has avg_conf=0.9, avg_acc=1.0, gap=0.1, weight=1/4.
    Wait, that gives ECE=0.05, not zero. The only true-zero case is when
    the confidence matches the bin's empirical accuracy exactly. So we
    use a known-zero input: 8 samples at conf=0.1 with all wrong, and
    2 samples at conf=0.5 with 1 right and 1 wrong.
    """
    confs = [0.1] * 8 + [0.5, 0.5]
    correct = [False] * 8 + [True, False]
    # Bin [0, 0.1) has 8 samples, avg_conf=0.1, avg_acc=0.0, gap=0.1, weight=0.8
    # Bin [0.5, 0.6) has 2 samples, avg_conf=0.5, avg_acc=0.5, gap=0.0, weight=0.2
    # ECE = 0.1 * 0.8 + 0 = 0.08
    assert ece(confs, correct) == pytest.approx(0.08, abs=1e-9)


def test_ece_always_wrong_when_overconfident() -> None:
    confs = [1.0] * 10
    correct = [False] * 10
    assert ece(confs, correct) == pytest.approx(1.0)


def test_brier_basic() -> None:
    # Perfect predictions on 4 correct, 0 wrong => brier = 0.
    assert brier([1.0] * 4, [True] * 4) == pytest.approx(0.0)
    # Perfect predictions on 4 wrong => brier = 0.
    assert brier([0.0] * 4, [False] * 4) == pytest.approx(0.0)
    # Random: 50% confidence on 4 right, 4 wrong => brier = 0.25
    assert brier([0.5] * 8, [True, False] * 4) == pytest.approx(0.25, abs=1e-6)


def test_auroc_perfect_ranking() -> None:
    # All correct samples have higher confidence than all wrong ones.
    confs = [0.9, 0.8, 0.2, 0.1]
    correct = [True, True, False, False]
    assert auroc(confs, correct) == pytest.approx(1.0)


def test_auroc_random_ranking() -> None:
    confs = [0.9, 0.1, 0.8, 0.2]
    correct = [True, False, True, False]
    # Perfectly ranked => 1.0
    assert auroc(confs, correct) == pytest.approx(1.0)


def test_auroc_all_one_class() -> None:
    assert auroc([0.5, 0.6, 0.7], [True, True, True]) == 0.5
    assert auroc([0.5, 0.6, 0.7], [False, False, False]) == 0.5


# ── coverage_at_target_accuracy ────────────────────────────────────


def test_coverage_at_target_accuracy_perfect_calibration() -> None:
    confs = [0.9, 0.8, 0.7, 0.1, 0.05, 0.0]
    correct = [True, True, True, False, False, False]
    coverage, threshold = coverage_at_target_accuracy(confs, correct, 0.95)
    assert coverage == pytest.approx(0.5, abs=1e-9)
    # Threshold should fall between 0.7 (last accepted) and 0.1 (first rejected).
    assert 0.1 < threshold <= 0.7


def test_coverage_at_target_accuracy_handles_empty() -> None:
    coverage, threshold = coverage_at_target_accuracy([], [], 0.95)
    assert coverage == 0.0
    assert threshold == 0.0


# ── reliability_diagram_text ───────────────────────────────────────


def test_reliability_diagram_text_runs() -> None:
    confs = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]
    correct = [False, False, True, True, True, True, True, True]
    text = reliability_diagram_text(confs, correct)
    assert "conf" in text
    assert "0.10-0.20" in text
    assert "histogram" in text


def test_render_reliability_diagram_writes_file(tmp_path: Path) -> None:
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        pytest.skip("matplotlib not available")
    confs = [0.1, 0.5, 0.9, 0.2, 0.6, 0.8]
    correct = [False, True, True, False, True, True]
    out = tmp_path / "reliability.png"
    render_reliability_diagram(confs, correct, str(out))
    assert out.exists()
    assert out.stat().st_size > 1000  # a real PNG is non-trivial


# ── build_report ──────────────────────────────────────────────────


def test_build_report_end_to_end() -> None:
    samples = [
        {"expected": {"a": "x", "b": 1}},
        {"expected": {"a": "y", "b": 2}},
    ]
    predictions = [
        {"result": {"a": "x", "b": 1}},
        {"result": {"a": "y", "b": 99}},
    ]
    confidences = [
        {"a": 0.95, "b": 0.9},
        {"a": 0.8, "b": 0.6},
    ]
    report = build_report(samples, predictions, confidences, required_fields=("a",))
    assert isinstance(report, EvalReport)
    assert report.sample_count == 2
    # 3 of 4 fields are correct.
    assert report.field_f1 == pytest.approx(0.75, abs=1e-9)
    assert 0.0 <= report.ece <= 1.0
    assert 0.0 <= report.auroc <= 1.0
    assert 0.0 <= report.coverage_at_95 <= 1.0
    d = report.to_dict()
    json.dumps(d)  # must be serializable
    assert "field_f1" in d
    assert "per_field_f1" in d
