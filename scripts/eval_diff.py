"""Compare the two most recent eval runs and print metric deltas.

Usage::

    just eval-diff

Output is a markdown table that can be pasted into a PR
description or a Slack thread. Exit code is 0 on improvement or
no change, 1 on regression (any key metric dropped by more than
the configured threshold).
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Where eval runs land (set by scripts/run_eval.py; kept here for
# clarity, not duplicated to avoid drift).
DEFAULT_RUNS_DIR = Path("eval/runs")

# Metric direction: "up" = higher is better, "down" = lower is better.
# Used to color the delta and decide improvement vs regression.
DIRECTION = {
    "field_f1": "up",
    "field_precision": "up",
    "field_recall": "up",
    "schema_conformance": "up",
    "ece": "down",
    "brier": "down",
    "auroc": "up",
    "coverage_at_target_accuracy_0.95": "up",
    "threshold_at_target_accuracy_0.95": "down",
    "sample_count": "up",
}

# A drop of more than this on an "up" metric (or rise on a "down"
# metric) is a regression. Calibrated against the historical
# CORD noise floor (~0.5pp on field_f1).
REGRESSION_DELTA = {
    "field_f1": 0.02,
    "ece": 0.02,
    "auroc": 0.02,
}


def _load_runs(runs_dir: Path) -> list[dict]:
    out: list[dict] = []
    for p in sorted(runs_dir.glob("*.json")):
        try:
            out.append((p, json.loads(p.read_text())))
        except json.JSONDecodeError:
            logger.warning("skipping malformed run file %s", p)
    return out


def _delta(curr: float, prev: float) -> float:
    return curr - prev


def main(runs_dir: str = "eval/runs") -> int:
    """Print a markdown diff of the two most recent runs. Returns 0
    on improvement or no change, 1 on regression."""
    runs = _load_runs(Path(runs_dir))
    if len(runs) < 2:
        print(f"need at least 2 eval runs in {runs_dir}; found {len(runs)}")
        return 0
    prev_path, prev = runs[-2]
    curr_path, curr = runs[-1]
    print(f"# Eval diff: {prev_path.name} -> {curr_path.name}\n")
    print("| metric | prev | curr | delta | dir |")
    print("|--------|------|------|-------|-----|")
    keys = sorted(set(prev) | set(curr))
    keys = [k for k in keys if isinstance(prev.get(k), (int, float)) and k != "sample_count"]
    has_regression = False
    for k in keys:
        p = prev.get(k, 0.0)
        c = curr.get(k, 0.0)
        d = _delta(c, p)
        direction = DIRECTION.get(k, "up")
        is_regression = False
        if (direction == "up" and d < 0 and abs(d) > REGRESSION_DELTA.get(k, 0.05)) or (
            direction == "down" and d > 0 and abs(d) > REGRESSION_DELTA.get(k, 0.05)
        ):
            is_regression = True
        marker = "  ⚠️" if is_regression else ""
        if is_regression:
            has_regression = True
        print(f"| `{k}` | {p:.4f} | {c:.4f} | {d:+.4f} | {direction}{marker} |")
    return 1 if has_regression else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    sys.exit(main())
