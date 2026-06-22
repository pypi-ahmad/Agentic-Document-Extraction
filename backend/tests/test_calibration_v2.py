"""Tests for the v0.5.0 composite confidence (calibration v2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.eval.calibration_v2 import (
    DEFAULT_WEIGHTS,
    CompositeCalibrator,
    CompositeSignals,
    composite_confidence,
    evidence_coverage,
    fit_composite_weights,
    load_weights,
    logprob_to_confidence,
    save_weights,
    verifier_agreement,
)

# ── logprob_to_confidence ─────────────────────────────────────────


def test_logprob_to_confidence_zero() -> None:
    assert logprob_to_confidence(0.0) == 1.0


def test_logprob_to_confidence_negative_one() -> None:
    assert logprob_to_confidence(-1.0) == pytest.approx(0.3679, rel=1e-3)


def test_logprob_to_confidence_clamps_very_negative() -> None:
    assert logprob_to_confidence(-100.0) > 0.0


def test_logprob_to_confidence_none() -> None:
    assert logprob_to_confidence(None) == 0.5


def test_logprob_to_confidence_inf() -> None:
    assert logprob_to_confidence(float("inf")) == 0.0
    assert logprob_to_confidence(float("-inf")) == 0.0


def test_logprob_to_confidence_clamps_positive() -> None:
    # Positive logprobs are not possible; clamp to 0 → 1.0
    assert logprob_to_confidence(0.5) == 1.0


# ── composite_confidence ──────────────────────────────────────────


def test_composite_confidence_full_signals() -> None:
    signals = CompositeSignals(
        logprob_confidence=1.0, verifier_agreement=1.0, evidence_coverage=1.0
    )
    assert composite_confidence(signals) == 1.0


def test_composite_confidence_zero_signals() -> None:
    signals = CompositeSignals(
        logprob_confidence=0.0, verifier_agreement=0.0, evidence_coverage=0.0
    )
    assert composite_confidence(signals) == 0.0


def test_composite_confidence_default_weights() -> None:
    """Default weights sum-normalized for available signals."""

    signals = {"logprob_confidence": 1.0, "verifier_agreement": 0.5, "evidence_coverage": 0.0}
    score = composite_confidence(signals)
    # Only logprob (1.0) and verifier (0.5) carry weight when evidence is 0
    assert 0 < score < 1


def test_composite_confidence_missing_logprob() -> None:
    signals = {"verifier_agreement": 1.0, "evidence_coverage": 1.0}
    score = composite_confidence(signals)
    # Re-normalized over verifier + evidence
    assert score == 1.0


def test_composite_confidence_clamps_inputs() -> None:
    signals = CompositeSignals(
        logprob_confidence=2.0, verifier_agreement=-0.5, evidence_coverage=0.5
    )
    score = composite_confidence(signals)
    assert 0.0 <= score <= 1.0


def test_composite_confidence_custom_weights() -> None:
    signals = CompositeSignals(
        logprob_confidence=1.0, verifier_agreement=0.0, evidence_coverage=0.0
    )
    score = composite_confidence(
        signals, weights={"logprob": 1.0, "verifier": 0.0, "evidence": 0.0}
    )
    assert score == 1.0


def test_composite_confidence_zero_weight_total() -> None:
    signals = CompositeSignals()
    assert (
        composite_confidence(signals, weights={"logprob": 0, "verifier": 0, "evidence": 0}) == 0.0
    )


def test_composite_confidence_accepts_dict() -> None:
    score = composite_confidence(
        {"logprob_confidence": 1.0, "verifier_agreement": 0.5, "evidence_coverage": 0.0}
    )
    assert 0.0 < score < 1.0


def test_composite_signals_to_dict() -> None:
    s = CompositeSignals(logprob_confidence=0.8, verifier_agreement=0.7, evidence_coverage=0.6)
    assert s.to_dict() == {
        "logprob_confidence": 0.8,
        "verifier_agreement": 0.7,
        "evidence_coverage": 0.6,
    }


# ── evidence_coverage ────────────────────────────────────────────


def test_evidence_coverage_empty() -> None:
    assert evidence_coverage({}) == 0.0


def test_evidence_coverage_with_dataclass() -> None:
    from app.services.extraction.evidence import Evidence, EvidenceMap

    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value=1, page=0, text_span="x"),
            "b": Evidence(field="b", value=2, page=0, text_span=""),
        }
    )
    assert evidence_coverage(m.evidences) == 0.5


def test_evidence_coverage_with_dicts() -> None:
    evs = {"a": {"text_span": "x"}, "b": {"text_span": ""}}
    assert evidence_coverage(evs) == 0.5


def test_evidence_coverage_require_bbox() -> None:
    from app.services.extraction.evidence import Evidence, EvidenceMap

    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value=1, page=0, text_span="x", bbox=(0.1, 0.1, 0.4, 0.2)),
            "b": Evidence(field="b", value=2, page=0, text_span="y", bbox=None),
        }
    )
    assert evidence_coverage(m.evidences, require_bbox=True) == 0.5


def test_evidence_coverage_require_bbox_no_evidences() -> None:
    assert evidence_coverage({}, require_bbox=True) == 0.0


# ── verifier_agreement ───────────────────────────────────────────


def test_verifier_agreement_none() -> None:
    assert verifier_agreement(None) == 0.0


def test_verifier_agreement_empty() -> None:
    assert verifier_agreement({}) == 0.0


def test_verifier_agreement_with_dataclass() -> None:
    from app.services.extraction.verifier import Verdict, VerifierOutput

    o = VerifierOutput(
        field_verdicts={
            "a": Verdict(field="a", verdict="agree"),
            "b": Verdict(field="b", verdict="disagree"),
        }
    )
    assert verifier_agreement(o) == 0.5


def test_verifier_agreement_with_dict() -> None:
    o = {
        "field_verdicts": {
            "a": {"verdict": "agree"},
            "b": {"verdict": "disagree"},
        }
    }
    assert verifier_agreement(o) == 0.5


def test_verifier_agreement_all_agree() -> None:
    from app.services.extraction.verifier import Verdict, VerifierOutput

    o = VerifierOutput(
        field_verdicts={
            "a": Verdict(field="a", verdict="agree"),
            "b": Verdict(field="b", verdict="agree"),
        }
    )
    assert verifier_agreement(o) == 1.0


# ── fit_composite_weights ────────────────────────────────────────


def test_fit_composite_weights_empty() -> None:
    assert fit_composite_weights([]) == DEFAULT_WEIGHTS


def test_fit_composite_weights_perfect_signal() -> None:
    """When the logprob signal perfectly predicts correctness, its weight
    should grow and the others should shrink."""

    samples = [
        {"logprob": 1.0, "verifier": 0.0, "evidence": 0.0, "correct": 1},
        {"logprob": 0.0, "verifier": 0.0, "evidence": 0.0, "correct": 0},
    ] * 50
    weights = fit_composite_weights(samples, learning_rate=0.1, steps=200)
    assert weights["logprob"] > 0.5  # dominates
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-3)


def test_fit_composite_weights_normalized() -> None:
    samples = [
        {"logprob": 0.5, "verifier": 0.5, "evidence": 0.5, "correct": 1},
        {"logprob": 0.3, "verifier": 0.4, "evidence": 0.2, "correct": 0},
    ] * 20
    weights = fit_composite_weights(samples)
    assert sum(weights.values()) == pytest.approx(1.0, rel=1e-3)
    for v in weights.values():
        assert v >= 0.0


# ── CompositeCalibrator ──────────────────────────────────────────


def test_composite_calibrator_default() -> None:
    c = CompositeCalibrator()
    score = c.confidence(logprob_confidence=0.0)
    assert 0.0 <= score <= 1.0


def test_composite_calibrator_full() -> None:
    from app.services.extraction.verifier import Verdict, VerifierOutput

    c = CompositeCalibrator()
    o = VerifierOutput(
        field_verdicts={"a": Verdict(field="a", verdict="agree")},
    )
    from app.services.extraction.evidence import Evidence, EvidenceMap

    m = EvidenceMap(evidences={"a": Evidence(field="a", value=1, page=0, text_span="x")})
    score = c.confidence(logprob_confidence=0.0, verifier_output=o, evidences=m.evidences)
    # All three signals contribute; logprob at 0 → 1.0, verifier agree → 1.0,
    # evidence coverage → 1.0 → composite = 1.0
    assert score == pytest.approx(1.0, rel=1e-3)


def test_composite_calibrator_empty() -> None:
    c = CompositeCalibrator()
    score = c.confidence()
    assert 0.0 <= score <= 1.0


def test_composite_calibrator_require_bbox() -> None:
    from app.services.extraction.evidence import Evidence, EvidenceMap

    c = CompositeCalibrator(require_bbox=True)
    m = EvidenceMap(evidences={"a": Evidence(field="a", value=1, page=0, text_span="x", bbox=None)})
    score = c.confidence(logprob_confidence=0.0, evidences=m.evidences)
    # logprob → 1.0; verifier → 0.0; evidence → 0.0 (no bbox). Re-normalized
    # over logprob only → 1.0
    assert score == pytest.approx(1.0, rel=1e-3)


def test_composite_calibrator_custom_weights() -> None:
    c = CompositeCalibrator(weights={"logprob": 0.0, "verifier": 0.0, "evidence": 1.0})
    from app.services.extraction.evidence import Evidence, EvidenceMap

    m = EvidenceMap(evidences={"a": Evidence(field="a", value=1, page=0, text_span="x")})
    score = c.confidence(evidences=m.evidences)
    assert score == 1.0


# ── save / load weights round-trip ──────────────────────────────


def test_save_load_weights_round_trip(tmp_path: Path) -> None:
    weights = {"logprob": 0.5, "verifier": 0.3, "evidence": 0.2}
    path = tmp_path / "weights.json"
    save_weights(weights, path)
    loaded = load_weights(path)
    assert loaded == weights


def test_load_weights_schema_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "weights.json"
    path.write_text(json.dumps({"schema_version": 1, "weights": {"foo": 1.0}}))
    # v0.4.0 schema → use defaults
    loaded = load_weights(path)
    assert loaded == DEFAULT_WEIGHTS
