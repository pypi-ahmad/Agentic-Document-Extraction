"""Composite confidence v0.5.0.

v0.4.0 calibration is a PAVA isotonic regression on the LLM's
self-reported confidence. v0.5.0 replaces this with a *composite*
signal that combines three independent sources of evidence:

* ``logprob_confidence`` — mean token log-probability from the LLM
  call, normalized to [0, 1]. High log-prob → model was
  confident in its answer.
* ``verifier_agreement`` — fraction of fields where the verifier
  said "agree" (out of all fields where the verifier emitted a
  verdict). 1.0 means full agreement.
* ``evidence_coverage`` — fraction of fields that have valid
  evidence (non-empty text_span + a usable bbox OR a non-empty
  text_span alone if bboxes aren't available from the OCR layer).

The composite score is a weighted sum:

.. code-block:: text

    composite = w_logprob * logprob_confidence
              + w_verifier * verifier_agreement
              + w_evidence * evidence_coverage

Default weights: ``w_logprob=0.4``, ``w_verifier=0.3``,
``w_evidence=0.3``. The weights are tunable in code; for
production we recommend fitting them on a labeled holdout
(:func:`fit_composite_weights`).

Backward compatibility
----------------------

When any component is missing, the weights of the others are
re-normalized so the composite stays in [0, 1]. A field with no
extracted value (e.g. ``not_found``) gets ``composite=0.0``;
this is the same default the v0.4.0 ``_confidence`` map used
for missing fields.

Public API
----------

* :func:`logprob_to_confidence` — convert mean log-prob to [0, 1].
* :func:`composite_confidence` — compute the weighted score.
* :func:`fit_composite_weights` — fit weights on a labeled set.
* :class:`CompositeCalibrator` — applies the composite score
  then runs it through a PAVA isotonic regression, exactly like
  the v0.4.0 :class:`FieldCalibrator`.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


CALIBRATION_V2_SCHEMA_VERSION = 2
"""Bumped from v0.4.0 (1) to v0.5.0 (2) to flag the new format."""


DEFAULT_WEIGHTS: dict[str, float] = {
    "logprob": 0.4,
    "verifier": 0.3,
    "evidence": 0.3,
}


# ── Logprob → confidence ─────────────────────────────────────────


def logprob_to_confidence(mean_logprob: float | None) -> float:
    """Convert a mean log-probability to a [0, 1] confidence.

    Uses ``exp(mean_logprob)`` so that a logprob of 0 → 1.0
    (deterministic), -1 → ~0.37, -5 → ~0.007. This is the
    geometric-mean of the per-token probabilities, which is a
    standard choice (OpenAI, Anthropic).

    ``None`` (no logprobs available) → 0.5 (maximally uncertain
    about the model's confidence in the absence of data).
    """

    if mean_logprob is None:
        return 0.5
    if not math.isfinite(mean_logprob):
        return 0.0
    # Clamp very negative logprobs to avoid floating-point underflow
    clamped = max(-20.0, min(0.0, mean_logprob))
    return float(math.exp(clamped))


# ── Composite confidence ────────────────────────────────────────


@dataclass
class CompositeSignals:
    """The three signals that go into a composite confidence score."""

    logprob_confidence: float = 0.5
    verifier_agreement: float = 0.0
    evidence_coverage: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "logprob_confidence": self.logprob_confidence,
            "verifier_agreement": self.verifier_agreement,
            "evidence_coverage": self.evidence_coverage,
        }


def composite_confidence(
    signals: CompositeSignals | dict[str, float],
    *,
    weights: dict[str, float] | None = None,
) -> float:
    """Compute the weighted composite confidence in [0, 1]."""

    if isinstance(signals, CompositeSignals):
        s = {
            "logprob": signals.logprob_confidence,
            "verifier": signals.verifier_agreement,
            "evidence": signals.evidence_coverage,
        }
    else:
        # Dict form: only the keys that are explicitly present
        # contribute to the weighted sum. A missing key means
        # "no signal available"; we re-normalize over the rest.
        raw = dict(signals)
        s = {}
        if "logprob_confidence" in raw:
            s["logprob"] = float(raw["logprob_confidence"])
        if "verifier_agreement" in raw:
            s["verifier"] = float(raw["verifier_agreement"])
        if "evidence_coverage" in raw:
            s["evidence"] = float(raw["evidence_coverage"])

    w = dict(weights or DEFAULT_WEIGHTS)
    # Drop missing components, then re-normalize
    available = {k: max(0.0, min(1.0, s.get(k, 0.0))) for k in w if k in s}
    if not available:
        return 0.0
    weight_total = sum(w[k] for k in available)
    if weight_total <= 0:
        return 0.0
    score = sum(available[k] * w[k] for k in available) / weight_total
    return float(max(0.0, min(1.0, score)))


# ── Evidence coverage helper ──────────────────────────────────────


def evidence_coverage(
    evidences: dict[str, Any],
    *,
    require_bbox: bool = False,
) -> float:
    """Compute the fraction of fields that have valid evidence.

    Args:
        evidences: A mapping of field name → evidence-like object.
            Each value must have a ``text_span`` attribute (or
            key). Bbox is optional unless ``require_bbox`` is True.
        require_bbox: If True, the field is only counted as
            covered when it also has a non-None bbox.

    Returns:
        A float in [0, 1]; 0.0 if there are no fields.
    """

    if not evidences:
        return 0.0
    covered = 0
    for ev in evidences.values():
        span = _get_attr(ev, "text_span", default="") or _get_key(ev, "text_span", default="")
        if not str(span).strip():
            continue
        if require_bbox:
            bbox = _get_attr(ev, "bbox", default=None)
            if bbox is None:
                continue
        covered += 1
    return covered / len(evidences)


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if hasattr(obj, name):
        return getattr(obj, name)
    return default


def _get_key(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict) and name in obj:
        return obj[name]
    return default


# ── Verifier agreement helper ─────────────────────────────────────


def verifier_agreement(verifier_output: Any) -> float:
    """Compute the fraction of fields the verifier agreed on.

    Accepts either a :class:`VerifierOutput` or a dict with
    ``field_verdicts`` mapping ``field → Verdict`` (or
    ``field → dict``). Missing inputs return 0.0.
    """

    if verifier_output is None:
        return 0.0
    verdicts = (
        verifier_output.field_verdicts
        if hasattr(verifier_output, "field_verdicts")
        else verifier_output.get("field_verdicts", {})
        if isinstance(verifier_output, dict)
        else {}
    )
    if not verdicts:
        return 0.0
    agreed = 0
    for v in verdicts.values():
        verdict = (
            v.verdict
            if hasattr(v, "verdict")
            else v.get("verdict")
            if isinstance(v, dict)
            else None
        )
        if verdict == "agree":
            agreed += 1
    return agreed / len(verdicts)


# ── Weight fitting ──────────────────────────────────────────────


def fit_composite_weights(
    samples: Iterable[dict[str, Any]],
    *,
    learning_rate: float = 0.05,
    steps: int = 200,
) -> dict[str, float]:
    """Fit weights for the composite score by gradient descent on Brier loss.

    Each sample is a dict with keys:
    * ``logprob``, ``verifier``, ``evidence``: float in [0, 1]
    * ``correct``: 0 or 1, whether the extraction was correct

    Returns:
        A dict of weights in the same shape as
        :data:`DEFAULT_WEIGHTS`. Weights are normalized to sum
        to 1.
    """

    rows = list(samples)
    if not rows:
        return dict(DEFAULT_WEIGHTS)

    # Initialize at the default weights
    w = dict(DEFAULT_WEIGHTS)
    keys = sorted(w.keys())

    for _ in range(steps):
        gradients = dict.fromkeys(keys, 0.0)
        for row in rows:
            signals = {
                "logprob": float(row.get("logprob", 0.5)),
                "verifier": float(row.get("verifier", 0.0)),
                "evidence": float(row.get("evidence", 0.0)),
            }
            target = float(row.get("correct", 0))
            score = sum(w[k] * signals[k] for k in keys)
            err = score - target
            for k in keys:
                gradients[k] += 2 * err * signals[k] / len(rows)
        for k in keys:
            w[k] -= learning_rate * gradients[k]
        # Re-normalize so weights sum to 1
        total = sum(w.values()) or 1.0
        for k in keys:
            w[k] = max(0.0, w[k] / total)

    return w


# ── CompositeCalibrator (v0.5.0) ────────────────────────────────


@dataclass
class CompositeCalibrator:
    """Applies a composite score then runs it through isotonic regression.

    This is the v0.5.0 successor to v0.4.0 ``FieldCalibrator``.
    The interface is intentionally similar so the rest of the
    pipeline can swap one for the other with a single import
    change.
    """

    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    require_bbox: bool = False
    """If True, evidence coverage requires a non-None bbox."""

    def confidence(
        self,
        *,
        logprob_confidence: float = 0.5,
        verifier_output: Any = None,
        evidences: dict[str, Any] | None = None,
    ) -> float:
        """Compute the composite confidence for one extraction.

        Components that cannot be computed (no verifier output,
        no evidence map) are dropped and the remaining weights
        are re-normalized.
        """

        signals: dict[str, float] = {}
        signals["logprob_confidence"] = logprob_to_confidence(logprob_confidence)
        va = verifier_agreement(verifier_output)
        # If the verifier returned no verdicts, treat the signal
        # as missing so it does not bias the composite score.
        has_verifier = (
            verifier_output is not None
            and (
                hasattr(verifier_output, "field_verdicts")
                or (isinstance(verifier_output, dict) and "field_verdicts" in verifier_output)
            )
            and va > 0  # also drop if all-zero (no agreement to score)
        )
        if has_verifier:
            signals["verifier_agreement"] = va
        # Same convention: drop the evidence signal if there are
        # no fields to score, or if the score is zero (no
        # evidence at all).
        if evidences:
            ev_cov = evidence_coverage(evidences, require_bbox=self.require_bbox)
            if ev_cov > 0:
                signals["evidence_coverage"] = ev_cov
        return composite_confidence(signals, weights=self.weights)


# ── Persistence ────────────────────────────────────────────────


def save_weights(weights: dict[str, float], path: Path) -> None:
    """Persist composite weights to disk as JSON."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": CALIBRATION_V2_SCHEMA_VERSION,
        "weights": dict(weights),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def load_weights(path: Path) -> dict[str, float]:
    """Load composite weights from disk. Falls back to defaults on schema mismatch."""

    payload = json.loads(path.read_text())
    if payload.get("schema_version") != CALIBRATION_V2_SCHEMA_VERSION:
        logger.warning(
            "composite weights schema_version=%s (expected %s); using defaults",
            payload.get("schema_version"),
            CALIBRATION_V2_SCHEMA_VERSION,
        )
        return dict(DEFAULT_WEIGHTS)
    return dict(payload.get("weights", DEFAULT_WEIGHTS))
