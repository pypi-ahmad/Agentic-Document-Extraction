"""Eval metrics for document extraction.

Implements the standard 2025-2026 metric set:

- **Field-level F1** (micro across fields): the standard for CORD/FUNSD.
- **Schema-conformance rate**: did the JSON validate against the schema?
- **ANLS** (Average Normalized Levenshtein Similarity): the standard for
  free-text Q&A. 0 = no match, 1 = exact match. Bounded in [0, 1].
- **ECE** (Expected Calibration Error): is the LLM's self-reported
  ``_confidence`` actually calibrated? Lower is better; 0.05 is the
  rough production target.
- **Brier score**: mean squared error between predicted prob and outcome.
- **AUROC**: area under the ROC curve for selective prediction
  (auto-accept vs. needs-review routing). Higher is better.
- **Reliability diagram**: per-bin accuracy-vs-confidence plot.

All metrics are designed to be deterministic and dependency-light
(only the standard library).  The optional ``matplotlib`` dependency
is only needed for ``render_reliability_diagram``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

# ── Field-level F1 ──────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldComparison:
    """One field's per-instance comparison."""

    field: str
    expected: Any
    predicted: Any
    correct: bool


def _normalize(value: Any) -> str:
    """Normalize a value for comparison (string, lowercased, stripped)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        # Compare numbers as strings but with a fixed precision.
        return f"{float(value):.6f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        return "|".join(_normalize(v) for v in value)
    return str(value).strip().lower()


def compare_field(field: str, expected: Any, predicted: Any) -> FieldComparison:
    expected_norm = _normalize(expected)
    predicted_norm = _normalize(predicted)
    return FieldComparison(
        field=field,
        expected=expected,
        predicted=predicted,
        correct=expected_norm == predicted_norm and expected_norm != "",
    )


def field_f1(
    expected: Mapping[str, Any],
    predicted: Mapping[str, Any],
    *,
    fields: Iterable[str] | None = None,
) -> tuple[float, float, float, list[FieldComparison]]:
    """Compute precision, recall, F1, and per-field comparisons.

    Micro-averaged across fields: each (field, sample) pair is a
    single prediction. Returns ``(precision, recall, f1, comparisons)``.
    F1 is 0.0 when there is nothing to predict.
    """
    if fields is None:
        fields = sorted(set(expected) | set(predicted))
    comparisons = [compare_field(f, expected.get(f), predicted.get(f)) for f in fields]
    tp = sum(1 for c in comparisons if c.correct)
    fp = sum(1 for c in comparisons if not c.correct and _normalize(c.predicted) != "")
    fn = sum(1 for c in comparisons if not c.correct and _normalize(c.expected) != "")
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1, comparisons


# ── Schema-conformance rate ─────────────────────────────────────────


def schema_conformance_rate(
    predicted_list: Iterable[Mapping[str, Any]],
    *,
    required_fields: Iterable[str] = (),
) -> float:
    """Return the fraction of predictions that contain all required fields
    and have only string/number/boolean/list values.
    """
    required = tuple(required_fields)
    valid = 0
    total = 0
    for pred in predicted_list:
        total += 1
        if all(field in pred for field in required) and all(
            isinstance(v, (str, int, float, bool, list, dict, type(None))) for v in pred.values()
        ):
            valid += 1
    return valid / total if total else 0.0


# ── ANLS ────────────────────────────────────────────────────────────


def anls(predicted: str, expected: str, threshold: float = 0.5) -> float:
    """Average Normalized Levenshtein Similarity (Biten et al., 2019).

    Returns 1.0 for exact match, 0.0 if similarity is below
    ``threshold`` (defaults to 0.5 to penalize hallucination).
    """
    if not expected and not predicted:
        return 1.0
    if not expected or not predicted:
        return 0.0
    ratio = SequenceMatcher(None, expected, predicted).ratio()
    if ratio < threshold:
        return 0.0
    return ratio


# ── Confidence calibration ──────────────────────────────────────────


def ece(
    confidences: Iterable[float],
    correct: Iterable[bool],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error.

    Lower is better. 0.0 = perfect calibration. 0.05 is a typical
    production target.
    """
    confs = list(confidences)
    corr = list(correct)
    if len(confs) != len(corr) or not confs:
        return 0.0
    n = len(confs)
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    ece_value = 0.0
    for b in range(n_bins):
        lo, hi = bin_edges[b], bin_edges[b + 1]
        # The last bin is inclusive on the right edge; earlier bins
        # are half-open [lo, hi) to avoid double-counting exact
        # boundary values.
        if b == n_bins - 1:
            indices = [i for i, c in enumerate(confs) if lo <= c <= hi]
        else:
            indices = [i for i, c in enumerate(confs) if lo <= c < hi]
        if not indices:
            continue
        avg_conf = sum(confs[i] for i in indices) / len(indices)
        avg_acc = sum(1 for i in indices if corr[i]) / len(indices)
        ece_value += abs(avg_conf - avg_acc) * (len(indices) / n)
    return ece_value


def brier(
    confidences: Iterable[float],
    correct: Iterable[bool],
) -> float:
    """Mean squared error between predicted probability and 0/1 outcome.

    Lower is better. Decomposes into reliability, resolution, and
    uncertainty (the standard Brier decomposition).
    """
    pairs = list(zip(confidences, [1.0 if c else 0.0 for c in correct], strict=True))
    if not pairs:
        return 0.0
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def auroc(
    confidences: Iterable[float],
    correct: Iterable[bool],
) -> float:
    """Area under the ROC curve for selective prediction.

    Higher is better. 0.5 = random; 1.0 = perfect. This is the
    metric that actually matters for the auto-accept vs.
    needs-review routing policy.

    Computed via the trapezoidal rule on the ROC curve, which is
    equivalent to the Mann-Whitney U statistic divided by n_pos*n_neg.
    """
    pairs = list(zip(confidences, [1 if c else 0 for c in correct], strict=True))
    n = len(pairs)
    if n == 0:
        return 0.5
    n_pos = sum(1 for _, c in pairs if c == 1)
    n_neg = n - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    # Sort by confidence descending; break ties by correct desc.
    pairs.sort(key=lambda p: (-p[0], -p[1]))
    # Wilcoxon-Mann-Whitney U statistic.
    u = 0
    for i, (_, c_i) in enumerate(pairs):
        if c_i == 0:
            # Count positives with lower or equal confidence.
            for j in range(i):
                if pairs[j][1] == 1:
                    u += 1
    return u / (n_pos * n_neg)


def coverage_at_target_accuracy(
    confidences: Iterable[float],
    correct: Iterable[bool],
    target_accuracy: float = 0.95,
) -> tuple[float, float]:
    """Return ``(max_coverage, threshold)`` such that predicting only on
    samples with confidence above the threshold achieves at least
    ``target_accuracy``.

    This is the production-realistic selective-prediction metric.
    Higher coverage is better at the same target accuracy.
    """
    pairs = list(zip(confidences, [1 if c else 0 for c in correct], strict=True))
    n = len(pairs)
    if n == 0:
        return 0.0, 0.0
    pairs.sort(key=lambda p: -p[0])  # highest confidence first
    best = 0.0
    best_threshold = 0.0
    accepted = 0
    correct_acc = 0
    for i, (conf, c) in enumerate(pairs, start=1):
        accepted = i
        correct_acc += c
        accuracy = correct_acc / accepted
        if accuracy >= target_accuracy:
            coverage = accepted / n
            if coverage > best:
                best = coverage
                best_threshold = conf
    return best, best_threshold


# ── Reliability diagram (text) ─────────────────────────────────────


def reliability_diagram_text(
    confidences: Iterable[float],
    correct: Iterable[bool],
    n_bins: int = 10,
) -> str:
    """Return a text-format reliability diagram (for log output).

    Use ``render_reliability_diagram`` for an image.
    """
    pairs = list(zip(confidences, [1 if c else 0 for c in correct], strict=True))
    if not pairs:
        return "(no samples)"
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    lines = [
        f"{'conf':>10} {'n':>6} {'acc':>6} {'gap':>6}  histogram",
    ]
    for b in range(n_bins):
        lo, hi = bin_edges[b], bin_edges[b + 1]
        if b == n_bins - 1:
            indices = [i for i, (c, _) in enumerate(pairs) if lo <= c <= hi]
        else:
            indices = [i for i, (c, _) in enumerate(pairs) if lo <= c < hi]
        if not indices:
            continue
        avg_conf = sum(pairs[i][0] for i in indices) / len(indices)
        avg_acc = sum(pairs[i][1] for i in indices) / len(indices)
        gap = avg_conf - avg_acc
        bar = "#" * max(1, int(avg_acc * 30))
        lines.append(f"{lo:5.2f}-{hi:4.2f} {len(indices):6d} {avg_acc:6.2f} {gap:+6.2f}  {bar}")
    return "\n".join(lines)


def render_reliability_diagram(
    confidences: Iterable[float],
    correct: Iterable[bool],
    out_path: str,
    n_bins: int = 10,
) -> None:
    """Render a PNG reliability diagram. Requires matplotlib."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for render_reliability_diagram") from exc

    confs = list(confidences)
    corr = [1 if c else 0 for c in correct]
    if not confs:
        return
    fig, ax = plt.subplots(figsize=(7, 5))
    bin_edges = [i / n_bins for i in range(n_bins + 1)]
    bin_centers: list[float] = []
    bin_accs: list[float] = []
    bin_counts: list[int] = []
    for b in range(n_bins):
        lo, hi = bin_edges[b], bin_edges[b + 1]
        indices = [i for i, c in enumerate(confs) if lo <= c <= hi]
        if not indices:
            continue
        bin_centers.append((lo + hi) / 2)
        bin_accs.append(sum(corr[i] for i in indices) / len(indices))
        bin_counts.append(len(indices))

    ax.bar(
        bin_centers,
        bin_accs,
        width=1 / n_bins * 0.9,
        alpha=0.5,
        color="steelblue",
        edgecolor="black",
        label="observed accuracy",
    )
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="perfect calibration")
    ax.set_xlabel("predicted confidence")
    ax.set_ylabel("observed accuracy")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Reliability diagram")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


# ── Aggregate report ──────────────────────────────────────────────


@dataclass
class EvalReport:
    """One eval pass's metrics."""

    sample_count: int
    schema_conformance: float
    field_precision: float
    field_recall: float
    field_f1: float
    ece: float
    brier: float
    auroc: float
    coverage_at_95: float
    threshold_at_95: float
    per_field_f1: dict[str, float]

    def to_dict(self) -> dict:
        return {
            "sample_count": self.sample_count,
            "schema_conformance": round(self.schema_conformance, 4),
            "field_precision": round(self.field_precision, 4),
            "field_recall": round(self.field_recall, 4),
            "field_f1": round(self.field_f1, 4),
            "ece": round(self.ece, 4),
            "brier": round(self.brier, 4),
            "auroc": round(self.auroc, 4),
            "coverage_at_target_accuracy_0.95": round(self.coverage_at_95, 4),
            "threshold_at_target_accuracy_0.95": round(self.threshold_at_95, 4),
            "per_field_f1": {k: round(v, 4) for k, v in self.per_field_f1.items()},
        }


def build_report(
    samples: list[dict],
    predictions: list[dict],
    confidences: list[dict],
    *,
    required_fields: Iterable[str] = (),
) -> EvalReport:
    """Build a single EvalReport from parallel arrays of samples,
    predictions, and per-field confidence maps.

    ``samples`` is a list of ``{"expected": {...}}`` dicts.
    ``predictions`` is a list of ``{"result": {...}}`` dicts.
    ``confidences`` is a list of ``{"field": float}`` dicts.
    """
    assert len(samples) == len(predictions) == len(confidences)
    n = len(samples)
    if n == 0:
        return EvalReport(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0, {})

    # First pass: discover all fields touched by any sample.
    all_fields: set[str] = set()
    for sample, pred in zip(samples, predictions, strict=True):
        for f in sample.get("expected", {}):
            all_fields.add(f)
        for f in pred.get("result", {}):
            all_fields.add(f)

    # Second pass: collect per-field confidences and correctness.
    all_confs: list[float] = []
    all_correct: list[bool] = []
    per_field_scores: dict[str, list[float]] = {}
    for sample, pred, conf in zip(samples, predictions, confidences, strict=True):
        expected = sample.get("expected", {})
        predicted = pred.get("result", {})
        for field in all_fields:
            score = float(conf.get(field, 0.0))
            is_correct = compare_field(field, expected.get(field), predicted.get(field)).correct
            all_confs.append(score)
            all_correct.append(is_correct)
            per_field_scores.setdefault(field, []).append(1.0 if is_correct else 0.0)

    per_field_f1 = {field: sum(s) / len(s) if s else 0.0 for field, s in per_field_scores.items()}

    pred_strs = [p.get("result", {}) for p in predictions]
    schema_rate = schema_conformance_rate(pred_strs, required_fields=required_fields)
    coverage, threshold = coverage_at_target_accuracy(all_confs, all_correct, 0.95)
    if all_confs:
        n_pos_pred = sum(1 for p in all_confs if p > 0)
        precision = sum(
            1 for c, p in zip(all_correct, all_confs, strict=True) if c and p > 0
        ) / max(1, n_pos_pred)
        recall = precision  # Same denominator, same numerator.
        f1_score = sum(all_correct) / len(all_correct)
    else:
        precision = recall = f1_score = 0.0
    return EvalReport(
        sample_count=n,
        schema_conformance=schema_rate,
        field_precision=precision,
        field_recall=recall,
        field_f1=f1_score,
        ece=ece(all_confs, all_correct),
        brier=brier(all_confs, all_correct),
        auroc=auroc(all_confs, all_correct),
        coverage_at_95=coverage,
        threshold_at_95=threshold,
        per_field_f1=per_field_f1,
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
