"""Unit tests for the per-field isotonic calibration module.

Covers the PAVA implementation, the CalibrationMap lookup, the
FieldCalibrator fit/apply roundtrip, save/load JSON, and the
identity/over-confident cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.eval.calibration import (
    CALIBRATION_SCHEMA_VERSION,
    CalibrationMap,
    FieldCalibrator,
    _isotonic_pava,
    apply_calibration,
    fit_calibrator,
)

# ── PAVA ────────────────────────────────────────────────────────────


def test_pava_returns_same_length() -> None:
    xs = [0.1, 0.2, 0.3, 0.4, 0.5]
    ys = _isotonic_pava(xs, [1.0] * len(xs))
    assert len(ys) == len(xs)


def test_pava_is_monotone_non_decreasing() -> None:
    """Random or adversarial inputs must produce a non-decreasing output."""
    xs = [0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.6, 0.4, 0.5]
    ys = _isotonic_pava(xs, [1.0] * len(xs))
    for i in range(len(ys) - 1):
        assert ys[i] <= ys[i + 1] + 1e-12


def test_pava_passes_through_already_monotone() -> None:
    xs = [0.1, 0.3, 0.5, 0.7, 0.9]
    ys = _isotonic_pava(xs, [1.0] * len(xs))
    assert ys == pytest.approx(xs)


def test_pava_empty() -> None:
    assert _isotonic_pava([], []) == []


def test_pava_single() -> None:
    assert _isotonic_pava([0.5], [1.0]) == [0.5]


def test_pava_constant_collapses() -> None:
    """All-equal input should produce a single block of the same value."""
    xs = [0.5] * 10
    ys = _isotonic_pava(xs, [1.0] * len(xs))
    assert all(abs(y - 0.5) < 1e-12 for y in ys)


def test_pava_with_weights() -> None:
    """Heavier-weighted observations pull the pool more."""
    # PAVA preserves monotonicity of the input order; when input
    # is already non-decreasing, output equals input.
    xs = [0.1, 0.9]
    ys = _isotonic_pava(xs, [1.0, 1.0])
    assert ys == pytest.approx([0.1, 0.9])
    # With reversed order PAVA must pool them.
    ys_rev = _isotonic_pava([0.9, 0.1], [1.0, 1.0])
    assert ys_rev == pytest.approx([0.5, 0.5])
    # Heavier weight on the high value drags the pool up.
    ys_w = _isotonic_pava([0.9, 0.1], [1.0, 10.0])
    # Pool: 0.1 absorbed into 0.9 → weighted avg (0.9+1.0)/(1+10) = 1.9/11
    assert ys_w[1] == pytest.approx(1.9 / 11)


# ── CalibrationMap.apply ───────────────────────────────────────────


def test_calibration_map_apply_within_range() -> None:
    m = CalibrationMap(xs=(0.0, 0.5, 1.0), ys=(0.0, 0.4, 0.9))
    assert m.apply(0.25) == pytest.approx(0.2)
    assert m.apply(0.75) == pytest.approx(0.65)


def test_calibration_map_apply_clamps_below() -> None:
    m = CalibrationMap(xs=(0.0, 0.5, 1.0), ys=(0.0, 0.4, 0.9))
    assert m.apply(-0.1) == 0.0
    assert m.apply(0.0) == 0.0


def test_calibration_map_apply_clamps_above() -> None:
    m = CalibrationMap(xs=(0.0, 0.5, 1.0), ys=(0.0, 0.4, 0.9))
    assert m.apply(1.0) == 0.9
    assert m.apply(1.5) == 0.9


def test_calibration_map_apply_is_monotone() -> None:
    m = CalibrationMap(xs=(0.0, 0.3, 0.6, 0.9), ys=(0.0, 0.2, 0.5, 0.8))
    last = -1.0
    for c in [0.0, 0.1, 0.2, 0.3, 0.5, 0.6, 0.8, 0.9, 1.0]:
        v = m.apply(c)
        assert v >= last - 1e-12
        last = v


# ── FieldCalibrator ────────────────────────────────────────────────


def _make_sample(confs: dict[str, float], correct: dict[str, bool]) -> dict:
    return {"confidences": confs, "per_field_correct": correct}


def test_fit_calibrator_per_field_maps() -> None:
    samples = [
        _make_sample({"total": 0.9}, {"total": True}),
        _make_sample({"total": 0.9}, {"total": True}),
        _make_sample({"total": 0.9}, {"total": True}),
        _make_sample({"total": 0.9}, {"total": True}),
        _make_sample({"total": 0.9}, {"total": True}),
        _make_sample({"total": 0.2}, {"total": False}),
    ]
    c = fit_calibrator(samples)
    assert "total" in c.maps
    # Overconfident 0.9 should map to ~1.0 (since 5/5 correct).
    assert c.maps["total"].apply(0.9) == pytest.approx(1.0, abs=1e-6)
    # 0.2 should map to ~0.0.
    assert c.maps["total"].apply(0.2) == pytest.approx(0.0, abs=1e-6)


def test_fit_calibrator_drops_under_sampled_fields() -> None:
    samples = [
        _make_sample({"rare": 0.5}, {"rare": True}),
        _make_sample({"rare": 0.5}, {"rare": True}),
    ]
    c = fit_calibrator(samples, min_samples_per_field=5)
    # Not enough samples for a per-field map; the default still exists.
    assert "rare" not in c.maps
    assert c.default_isotonic is not None


def test_fit_calibrator_underconfident_pushed_up() -> None:
    """Conf=0.5 but always correct → calibration should map 0.5 to 1.0."""
    samples = [_make_sample({"x": 0.5}, {"x": True}) for _ in range(20)]
    c = fit_calibrator(samples)
    out = apply_calibration(c, {"x": 0.5})
    assert out["x"] > 0.9


def test_fit_calibrator_overconfident_pushed_down() -> None:
    """Conf=0.9 but always wrong → calibration should map 0.9 to 0.0."""
    samples = [_make_sample({"x": 0.9}, {"x": False}) for _ in range(20)]
    c = fit_calibrator(samples)
    out = apply_calibration(c, {"x": 0.9})
    assert out["x"] < 0.1


def test_fit_calibrator_identity_on_perfect_calibration() -> None:
    """When the LLM is already perfectly calibrated, the calibrator
    should leave the confidence roughly unchanged."""
    samples = []
    for conf in [0.1, 0.3, 0.5, 0.7, 0.9]:
        for _ in range(10):
            samples.append(
                _make_sample(
                    {"x": conf},
                    {"x": conf < 0.5 or (conf == 0.5 and _ % 2 == 0)},
                )
            )
    c = fit_calibrator(samples)
    out = apply_calibration(c, {"x": 0.5})
    # Should be close to 0.5 (the empirical accuracy of conf=0.5 in this set).
    assert 0.3 < out["x"] < 0.7


def test_field_calibrator_unknown_field_uses_default() -> None:
    samples = [_make_sample({"a": 0.5}, {"a": True}) for _ in range(10)]
    c = fit_calibrator(samples)
    # "z" is unknown → use the default mapping.
    out = apply_calibration(c, {"z": 0.5})
    assert "z" in out
    # Default is fitted on the only "a" pairs (all conf=0.5, all correct),
    # so 0.5 maps high.
    assert out["z"] > 0.9


def test_field_calibrator_unknown_field_no_default() -> None:
    """With no samples, no default mapping exists; unknown fields are
    passed through unchanged."""
    c = FieldCalibrator(maps={}, default_isotonic=None)
    out = apply_calibration(c, {"z": 0.42})
    assert out == {"z": 0.42}


# ── Save / load ────────────────────────────────────────────────────


def test_calibrator_save_load_roundtrip(tmp_path: Path) -> None:
    samples = [_make_sample({"a": 0.5}, {"a": True}) for _ in range(10)] + [
        _make_sample({"a": 0.9}, {"a": False}) for _ in range(10)
    ]
    c = fit_calibrator(samples)
    p = tmp_path / "cal.json"
    c.save(p)
    loaded = FieldCalibrator.load(p)
    assert loaded.maps.keys() == c.maps.keys()
    assert loaded.apply({"a": 0.5}) == pytest.approx(c.apply({"a": 0.5}))


def test_calibrator_save_human_readable_json(tmp_path: Path) -> None:
    """The artifact must be JSON (git-diffable, safe to commit), not pickle."""
    c = FieldCalibrator(
        maps={"x": CalibrationMap(xs=(0.0, 1.0), ys=(0.1, 0.9))},
        default_isotonic=CalibrationMap(xs=(0.0, 1.0), ys=(0.2, 0.8)),
        n_samples=42,
    )
    p = tmp_path / "cal.json"
    c.save(p)
    data = json.loads(p.read_text())
    assert data["n_samples"] == 42
    assert "x" in data["maps"]
    assert data["maps"]["x"]["xs"] == [0.0, 1.0]


def test_calibrator_load_rejects_newer_schema(tmp_path: Path) -> None:
    p = tmp_path / "future.json"
    p.write_text(json.dumps({"schema_version": 999}))
    with pytest.raises(ValueError, match="newer than supported"):
        FieldCalibrator.load(p)


def test_calibrator_load_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        FieldCalibrator.load(tmp_path / "missing.json")


def test_calibrator_schema_version_constant() -> None:
    assert CALIBRATION_SCHEMA_VERSION >= 1
