"""Tests for the v0.5.0 metric suite (TEDS, cell-F1, attribution, IoU, ...)."""

from __future__ import annotations

import pytest

from app.services.eval.metrics_v2 import (
    anls,
    bbox_iou,
    cell_precision_recall_f1,
    end_to_end_task_success_rate,
    evidence_attribution_accuracy,
    exact_match,
    exact_match_batch,
    header_match_accuracy,
    mean_bbox_iou,
    page_localization_accuracy,
    row_column_structure_accuracy,
    run_v2_suite,
    teds,
    token_f1,
    token_f1_batch,
)

# ── Exact Match ──────────────────────────────────────────────────


def test_exact_match_identical() -> None:
    assert exact_match("Acme Corp", "Acme Corp") == 1.0


def test_exact_match_normalizes_whitespace() -> None:
    assert exact_match("Acme   Corp", "Acme Corp") == 1.0


def test_exact_match_different() -> None:
    assert exact_match("Acme", "Globex") == 0.0


def test_exact_match_none() -> None:
    assert exact_match(None, "x") == 0.0
    assert exact_match("x", None) == 0.0


def test_exact_match_batch() -> None:
    assert exact_match_batch(["a", "b", "c"], ["a", "x", "c"]) == pytest.approx(2 / 3)


def test_exact_match_batch_empty() -> None:
    assert exact_match_batch([], []) == 0.0


# ── Token F1 ────────────────────────────────────────────────────


def test_token_f1_identical() -> None:
    assert token_f1("Acme Corp", "Acme Corp") == 1.0


def test_token_f1_partial() -> None:
    # "the quick brown fox" vs "the quick red fox"
    # common: the, quick, fox = 3; pred: 4; ref: 4
    # precision = 3/4, recall = 3/4, F1 = 0.75
    assert token_f1("the quick brown fox", "the quick red fox") == pytest.approx(0.75)


def test_token_f1_disjoint() -> None:
    assert token_f1("a b c", "x y z") == 0.0


def test_token_f1_empty() -> None:
    assert token_f1("", "") == 1.0
    assert token_f1("a", "") == 0.0


def test_token_f1_batch() -> None:
    assert token_f1_batch(["a b c", "x y z"], ["a b c", "x y z"]) == 1.0


# ── ANLS (re-export) ────────────────────────────────────────────


def test_anls_identical() -> None:
    assert anls("Acme", "Acme") == 1.0


def test_anls_different() -> None:
    assert anls("Acme", "Globex") < 1.0


# ── TEDS ────────────────────────────────────────────────────────


def test_teds_identical() -> None:
    assert teds([["A", "B"], ["1", "2"]], [["A", "B"], ["1", "2"]]) == 1.0


def test_teds_perfect_structure_different_values() -> None:
    # Same structure, different values: should be 0.0
    score = teds([["A", "B"], ["1", "2"]], [["X", "Y"], ["1", "2"]])
    assert score < 1.0


def test_teds_completely_different() -> None:
    score = teds([["A"]], [["B"]])
    assert 0.0 <= score < 1.0


def test_teds_empty_both_sides() -> None:
    assert teds([], []) == 1.0
    assert teds([[]], [[]]) == 1.0


def test_teds_empty_one_side() -> None:
    assert teds([], [["A"]]) < 1.0


# ── Cell P/R/F1 ─────────────────────────────────────────────────


def test_cell_prf_identical() -> None:
    out = cell_precision_recall_f1([["A", "B"]], [["A", "B"]])
    assert out == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_cell_prf_partial() -> None:
    # 3 of 4 cells match
    out = cell_precision_recall_f1([["A", "B"], ["1", "2"]], [["A", "X"], ["1", "2"]])
    assert out["precision"] == pytest.approx(0.75)
    assert out["recall"] == pytest.approx(0.75)
    assert out["f1"] == pytest.approx(0.75)


def test_cell_prf_numeric_tolerance() -> None:
    out = cell_precision_recall_f1([["1.0000001"]], [["1.0"]])
    assert out["f1"] == 1.0


def test_cell_prf_empty_both() -> None:
    out = cell_precision_recall_f1([], [])
    assert out == {"precision": 1.0, "recall": 1.0, "f1": 1.0}


# ── Row/Column structure accuracy ──────────────────────────────


def test_row_column_accuracy_match() -> None:
    out = row_column_structure_accuracy([["A", "B"], ["1", "2"]], [["X", "Y"], ["3", "4"]])
    assert out == {"row_accuracy": 1.0, "column_accuracy": 1.0}


def test_row_column_accuracy_mismatch() -> None:
    out = row_column_structure_accuracy([["A"]], [["A", "B"], ["1", "2"]])
    assert out["row_accuracy"] == 0.0
    assert out["column_accuracy"] == 0.0


def test_row_column_accuracy_partial() -> None:
    out = row_column_structure_accuracy(
        [["A", "B"], ["1", "2"]], [["X", "Y"], ["1", "2"], ["3", "4"]]
    )
    assert out["row_accuracy"] == 0.0
    assert out["column_accuracy"] == 1.0


def test_row_column_accuracy_empty() -> None:
    out = row_column_structure_accuracy([], [])
    assert out == {"row_accuracy": 1.0, "column_accuracy": 1.0}


# ── Header match ────────────────────────────────────────────────


def test_header_match_all_match() -> None:
    out = header_match_accuracy([["A", "B"], ["1", "2"]], [["A", "B"], ["3", "4"]])
    assert out == 1.0


def test_header_match_partial() -> None:
    out = header_match_accuracy([["A", "X"]], [["A", "B"]])
    assert out == 0.5


def test_header_match_empty() -> None:
    assert header_match_accuracy([], []) == 1.0
    assert header_match_accuracy([], [["A"]]) == 0.0


# ── Evidence attribution ───────────────────────────────────────


def test_evidence_attribution_full() -> None:
    from app.services.extraction.evidence import Evidence

    evs = {
        "a": Evidence(field="a", value=1, page=0, text_span="x"),
        "b": Evidence(field="b", value=2, page=0, text_span="y"),
    }
    assert evidence_attribution_accuracy(evs) == 1.0


def test_evidence_attribution_partial() -> None:
    from app.services.extraction.evidence import Evidence

    evs = {
        "a": Evidence(field="a", value=1, page=0, text_span="x"),
        "b": Evidence(field="b", value=2, page=0, text_span=""),
    }
    assert evidence_attribution_accuracy(evs) == 0.5


def test_evidence_attribution_dicts() -> None:
    evs = {"a": {"text_span": "x"}, "b": {"text_span": ""}}
    assert evidence_attribution_accuracy(evs) == 0.5


def test_evidence_attribution_empty() -> None:
    assert evidence_attribution_accuracy({}) == 0.0


# ── Bbox IoU ────────────────────────────────────────────────────


def test_bbox_iou_identical() -> None:
    a = (0.1, 0.1, 0.5, 0.5)
    assert bbox_iou(a, a) == pytest.approx(1.0)


def test_bbox_iou_disjoint() -> None:
    assert bbox_iou((0.0, 0.0, 0.2, 0.2), (0.8, 0.8, 1.0, 1.0)) == 0.0


def test_bbox_iou_none() -> None:
    assert bbox_iou(None, (0, 0, 0.5, 0.5)) == 0.0
    assert bbox_iou((0, 0, 0.5, 0.5), None) == 0.0


def test_mean_bbox_iou() -> None:
    pred = {"a": {"bbox": (0.1, 0.1, 0.5, 0.5)}, "b": {"bbox": (0.0, 0.0, 0.5, 0.5)}}
    ref = {"a": {"bbox": (0.1, 0.1, 0.5, 0.5)}, "b": {"bbox": (0.8, 0.8, 1.0, 1.0)}}
    # a: IoU 1.0; b: IoU 0.0; mean = 0.5
    assert mean_bbox_iou(pred, ref) == pytest.approx(0.5)


def test_mean_bbox_iou_no_common() -> None:
    assert mean_bbox_iou({"a": {"bbox": (0, 0, 1, 1)}}, {"b": {"bbox": (0, 0, 1, 1)}}) == 0.0


# ── Page localization ─────────────────────────────────────────


def test_page_localization_full_match() -> None:
    pred = {"a": {"page": 0}, "b": {"page": 1}}
    ref = {"a": {"page": 0}, "b": {"page": 1}}
    assert page_localization_accuracy(pred, ref) == 1.0


def test_page_localization_partial() -> None:
    pred = {"a": {"page": 0}, "b": {"page": 2}}
    ref = {"a": {"page": 0}, "b": {"page": 1}}
    assert page_localization_accuracy(pred, ref) == 0.5


def test_page_localization_missing() -> None:
    pred = {"a": {"page": 0}}
    ref = {"a": {"page": 0}, "b": {"page": 1}}
    # 1 of 2 common = 1.0, but b is missing from pred so contributes 0
    # Actually we only count common fields, so result is 1.0/1 = 1.0
    assert page_localization_accuracy(pred, ref) == 1.0


def test_page_localization_none_values() -> None:
    pred = {"a": {"page": None}}
    ref = {"a": {"page": 0}}
    assert page_localization_accuracy(pred, ref) == 0.0


# ── End-to-end task success ────────────────────────────────────


def test_e2e_all_match() -> None:
    pred = [{"vendor": "Acme", "total": 100}]
    ref = [{"vendor": "Acme", "total": 100}]
    assert end_to_end_task_success_rate(pred, ref) == 1.0


def test_e2e_one_diff() -> None:
    pred = [{"vendor": "Acme", "total": 100}]
    ref = [{"vendor": "Acme", "total": 200}]
    assert end_to_end_task_success_rate(pred, ref) == 0.0


def test_e2e_missing_field() -> None:
    pred = [{"vendor": "Acme"}]
    ref = [{"vendor": "Acme", "total": 100}]
    assert end_to_end_task_success_rate(pred, ref) == 0.0


def test_e2e_skips_meta() -> None:
    pred = [{"vendor": "Acme", "_meta": {"x": 1}}]
    ref = [{"vendor": "Acme"}]
    assert end_to_end_task_success_rate(pred, ref) == 1.0


def test_e2e_empty_both() -> None:
    assert end_to_end_task_success_rate([{}], [{}]) == 1.0


def test_e2e_empty_inputs() -> None:
    assert end_to_end_task_success_rate([], []) == 0.0


def test_e2e_case_insensitive() -> None:
    pred = [{"vendor": "ACME"}]
    ref = [{"vendor": "acme"}]
    assert end_to_end_task_success_rate(pred, ref) == 1.0


# ── run_v2_suite ───────────────────────────────────────────────


def test_run_v2_suite_kv_only() -> None:
    out = run_v2_suite(
        predictions_kv=["Acme", "100"],
        references_kv=["Acme", "100"],
    )
    assert out["em"] == 1.0
    assert out["token_f1"] == 1.0


def test_run_v2_suite_table_only() -> None:
    out = run_v2_suite(
        predictions_table=[[["A", "B"], ["1", "2"]]],
        references_table=[[["A", "B"], ["1", "2"]]],
    )
    assert out["teds"] == 1.0
    assert out["cell_f1"] == 1.0
    assert out["header_match_accuracy"] == 1.0
    assert out["row_accuracy"] == 1.0
    assert out["column_accuracy"] == 1.0


def test_run_v2_suite_with_evidences() -> None:
    from app.services.extraction.evidence import Evidence

    pred = {"a": Evidence(field="a", value=1, page=0, text_span="x", bbox=(0.1, 0.1, 0.4, 0.2))}
    ref = {"a": Evidence(field="a", value=1, page=0, text_span="x", bbox=(0.1, 0.1, 0.4, 0.2))}
    out = run_v2_suite(predicted_evidences=pred, expected_evidences=ref)
    assert out["evidence_attribution_accuracy"] == 1.0
    assert out["mean_bbox_iou"] == 1.0
    assert out["page_localization_accuracy"] == 1.0


def test_run_v2_suite_e2e() -> None:
    out = run_v2_suite(
        e2e_predictions=[{"vendor": "Acme"}],
        e2e_references=[{"vendor": "Acme"}],
    )
    assert out["end_to_end_task_success_rate"] == 1.0


def test_run_v2_suite_empty() -> None:
    out = run_v2_suite()
    assert out == {}


def test_run_v2_suite_full() -> None:
    out = run_v2_suite(
        predictions_kv=["Acme", "100"],
        references_kv=["Acme", "200"],
        predictions_table=[[["A", "B"]]],
        references_table=[[["A", "B"]]],
        e2e_predictions=[{"x": 1}],
        e2e_references=[{"x": 1}],
    )
    assert "em" in out
    assert "teds" in out
    assert "end_to_end_task_success_rate" in out
