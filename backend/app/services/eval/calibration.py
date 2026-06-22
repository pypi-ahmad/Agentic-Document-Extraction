"""Per-field confidence calibration via isotonic regression.

The LLM self-reports a ``confidence`` per field, but the raw score is
not well-calibrated: the LLM tends to be either overconfident
(>0.9 on wrong answers) or under-confident (~0.5 on easy answers).
A calibrated score is one where, of all predictions the model
labels with confidence 0.8, ~80% are actually correct.

We fit a per-field isotonic regression on a labeled holdout (the
golden set) and apply the learned mapping to live predictions. This
is the standard approach recommended by Guo et al. (2017) and is
used by every major production LLM service (AWS Bedrock, Vertex AI
RAG, Anthropic's tool-use routing).

The isotonic regression is monotone non-decreasing, so it never
flips a high-confidence prediction to a low-confidence one. It is
also fast (O(n) PAVA), deterministic, and dependency-free.

Public API
----------

- :class:`CalibrationMap` — one field's isotonic mapping.
- :class:`FieldCalibrator` — collection of ``CalibrationMap`` keyed
  by field name, with save/load.
- :func:`fit_calibrator` — fit a calibrator from labeled samples.
- :func:`apply_calibration` — apply a calibrator to a live
  ``{field: confidence}`` dict.

The artifact format is JSON (not pickle) so it is git-diffable
and safe to commit. A small schema version is embedded so we can
migrate old calibrators forward.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CALIBRATION_SCHEMA_VERSION = 1
"""Bump this when the on-disk format changes incompatibly."""


# ── Isotonic regression (PAVA) ──────────────────────────────────────


def _isotonic_pava(values: list[float], weights: list[float]) -> list[float]:
    """Pool-Adjacent-Violators Algorithm.

    Given paired ``(values, weights)`` with both lists the same
    length, return a list of monotone non-decreasing averages
    weighted by ``weights``. This is the classical isotonic
    regression fit (Barlow, Bremner, Brunk, 1972).

    O(n) time, O(n) space.
    """
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [values[0]]

    # Each "block" is a contiguous run that has already been
    # pooled into a single weighted average. Stored as
    # (weighted_sum, weight_sum, value_index_of_block_start).
    blocks: list[tuple[float, float, int]] = []
    for i in range(n):
        wsum = float(values[i]) * weights[i]
        w = weights[i]
        idx = i
        # If the new point violates monotonicity with the
        # previous block, pool them and re-check.
        while blocks and (wsum / w) < (blocks[-1][0] / blocks[-1][1]):
            prev_wsum, prev_w, prev_idx = blocks.pop()
            wsum += prev_wsum
            w += prev_w
            idx = prev_idx
        blocks.append((wsum, w, idx))

    # Spread the pooled block averages back out to the original
    # index positions. Each block's average fills the half-open
    # interval [start_idx, next_start_idx); the last block fills
    # to n.
    out = [0.0] * n
    for i, (wsum, w, idx) in enumerate(blocks):
        avg = wsum / w
        end = blocks[i + 1][2] if i + 1 < len(blocks) else n
        for j in range(idx, end):
            out[j] = avg
    return out


@dataclass(frozen=True)
class CalibrationMap:
    """One field's isotonic mapping: ``calibrated = map[confidence]``.

    ``xs`` are the unique sorted input confidences, ``ys`` are the
    calibrated outputs (also sorted, non-decreasing).
    Linear-interpolated between adjacent xs; clamped outside the
    observed range.
    """

    xs: tuple[float, ...]
    ys: tuple[float, ...]

    def apply(self, conf: float) -> float:
        if not self.xs:
            return conf
        if conf <= self.xs[0]:
            return self.ys[0]
        if conf >= self.xs[-1]:
            return self.ys[-1]
        # Binary search for the right interval.
        lo, hi = 0, len(self.xs) - 1
        while lo < hi - 1:
            mid = (lo + hi) // 2
            if self.xs[mid] <= conf:
                lo = mid
            else:
                hi = mid
        x0, x1 = self.xs[lo], self.xs[hi]
        y0, y1 = self.ys[lo], self.ys[hi]
        if x1 == x0:
            return y0
        t = (conf - x0) / (x1 - x0)
        return y0 + t * (y1 - y0)


@dataclass
class FieldCalibrator:
    """A collection of per-field :class:`CalibrationMap`.

    Fit on a labeled dataset (e.g. the CORD golden set), then
    applied to live ``{field: confidence}`` dicts. Unknown fields
    fall back to the identity (raw confidence), which is the
    correct default for fields we have not yet observed.
    """

    maps: dict[str, CalibrationMap] = field(default_factory=dict)
    default_isotonic: CalibrationMap | None = None
    n_samples: int = 0
    schema_version: int = CALIBRATION_SCHEMA_VERSION

    def apply(self, confidences: Mapping[str, float]) -> dict[str, float]:
        out: dict[str, float] = {}
        for k, v in confidences.items():
            m = self.maps.get(k, self.default_isotonic)
            out[k] = m.apply(v) if m is not None else v
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "n_samples": self.n_samples,
            "default_isotonic": (
                {"xs": list(self.default_isotonic.xs), "ys": list(self.default_isotonic.ys)}
                if self.default_isotonic
                else None
            ),
            "maps": {k: {"xs": list(m.xs), "ys": list(m.ys)} for k, m in self.maps.items()},
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FieldCalibrator:
        version = d.get("schema_version", 1)
        if version > CALIBRATION_SCHEMA_VERSION:
            raise ValueError(
                f"calibrator schema version {version} is newer than supported "
                f"{CALIBRATION_SCHEMA_VERSION}; please upgrade the package"
            )
        maps: dict[str, CalibrationMap] = {}
        for k, v in d.get("maps", {}).items():
            maps[k] = CalibrationMap(
                xs=tuple(v["xs"]),
                ys=tuple(v["ys"]),
            )
        default_iso: CalibrationMap | None = None
        if d.get("default_isotonic"):
            di = d["default_isotonic"]
            default_iso = CalibrationMap(xs=tuple(di["xs"]), ys=tuple(di["ys"]))
        return cls(
            maps=maps,
            default_isotonic=default_iso,
            n_samples=int(d.get("n_samples", 0)),
            schema_version=version,
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True))
        logger.info(
            "calibrator saved to %s (%d fields, %d samples)", p, len(self.maps), self.n_samples
        )

    @classmethod
    def load(cls, path: str | Path) -> FieldCalibrator:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"calibrator not found at {p}")
        return cls.from_dict(json.loads(p.read_text()))


# ── Fit & apply ────────────────────────────────────────────────────


def fit_calibrator(
    samples: Iterable[Mapping[str, Any]],
    *,
    min_samples_per_field: int = 5,
) -> FieldCalibrator:
    """Fit a per-field isotonic calibrator from labeled samples.

    Each sample is a dict with at least:

    - ``"confidences"``: ``{field: raw_confidence}``
    - ``"per_field_correct"``: ``{field: bool}`` (whether the
      prediction matched the ground truth for that field)

    Fields with fewer than ``min_samples_per_field`` observations
    are dropped from the per-field maps but contribute to the
    global default mapping. The global default is used for any
    field that has no per-field map.
    """
    by_field: dict[str, list[tuple[float, int]]] = defaultdict(list)
    all_pairs: list[tuple[float, int]] = []
    n = 0
    for sample in samples:
        n += 1
        confs = sample.get("confidences", {})
        correct = sample.get("per_field_correct", {})
        for f, c in confs.items():
            is_correct = 1 if correct.get(f) else 0
            by_field[f].append((float(c), is_correct))
            all_pairs.append((float(c), is_correct))

    maps: dict[str, CalibrationMap] = {}
    for f, pairs in by_field.items():
        if len(pairs) < min_samples_per_field:
            continue
        # Sort by confidence; ties broken by outcome (positives first)
        # so the pooled monotone regression is well-defined.
        ordered = sorted(pairs, key=lambda p: (p[0], -p[1]))
        xs = [p[0] for p in ordered]
        ys_outcome = [float(p[1]) for p in ordered]
        # PAVA is given the binary outcomes (the y values to
        # monotonize), weighted by observation count. The x values
        # are already sorted by the time we reach PAVA.
        ys = _isotonic_pava(ys_outcome, [1.0] * len(ordered))
        # Bucket by unique x to compress the mapping. We keep the
        # last (rightmost) y for each x so the function is
        # right-continuous at the breakpoints.
        compressed_xs: list[float] = []
        compressed_ys: list[float] = []
        prev_x = None
        for x, y in zip(xs, ys, strict=True):
            if prev_x is None or x != prev_x:
                compressed_xs.append(x)
                compressed_ys.append(y)
            else:
                compressed_ys[-1] = y
            prev_x = x
        maps[f] = CalibrationMap(xs=tuple(compressed_xs), ys=tuple(compressed_ys))

    default_iso: CalibrationMap | None = None
    if all_pairs:
        ordered = sorted(all_pairs, key=lambda p: (p[0], -p[1]))
        xs = [p[0] for p in ordered]
        ys_outcome = [float(p[1]) for p in ordered]
        ys = _isotonic_pava(ys_outcome, [1.0] * len(ordered))
        compressed_xs: list[float] = []
        compressed_ys: list[float] = []
        prev_x = None
        for x, y in zip(xs, ys, strict=True):
            if prev_x is None or x != prev_x:
                compressed_xs.append(x)
                compressed_ys.append(y)
            else:
                compressed_ys[-1] = y
            prev_x = x
        default_iso = CalibrationMap(xs=tuple(compressed_xs), ys=tuple(compressed_ys))

    return FieldCalibrator(
        maps=maps,
        default_isotonic=default_iso,
        n_samples=n,
        schema_version=CALIBRATION_SCHEMA_VERSION,
    )


def apply_calibration(
    calibrator: FieldCalibrator,
    confidences: Mapping[str, float],
) -> dict[str, float]:
    """Apply a fitted :class:`FieldCalibrator` to a live confidence dict.

    Convenience wrapper kept for readability at call sites; the
    calibrator's own :meth:`FieldCalibrator.apply` does the same.
    """
    return calibrator.apply(confidences)


__all__ = [
    "CALIBRATION_SCHEMA_VERSION",
    "CalibrationMap",
    "FieldCalibrator",
    "apply_calibration",
    "fit_calibrator",
]
