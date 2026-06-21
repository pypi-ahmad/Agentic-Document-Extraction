"""Fit a per-field isotonic confidence calibrator from a labeled run.

Reads a manifest produced by ``scripts/fetch_golden_set.py`` and
the eval runs under ``eval/runs/*.json``, joins them on sample
id, and writes a ``FieldCalibrator`` artifact (JSON) that the
runtime can load via ``confidence_calibration_path``.

Usage::

    just eval-fit-calibrator                              # defaults
    just eval-fit-calibrator eval/golden_set/v1/manifest.json ./calibration.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Iterable
from pathlib import Path

# Allow running as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.eval import fit_calibrator

logger = logging.getLogger(__name__)


def _load_runs(eval_runs_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not eval_runs_dir.exists():
        return out
    for p in sorted(eval_runs_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text())
        except json.JSONDecodeError:
            logger.warning("skipping malformed eval run file %s", p)
            continue
        for sample in data.get("samples", []):
            out.append(sample)
    return out


def _build_samples(runs: Iterable[dict]) -> list[dict]:
    samples: list[dict] = []
    for run in runs:
        confs = run.get("confidences", {})
        correct = run.get("per_field_correct", {})
        if not confs or not correct:
            continue
        samples.append({"confidences": confs, "per_field_correct": correct})
    return samples


def main(manifest_path: str, out_path: str) -> int:
    """Fit and save. Returns 0 on success, 1 on failure."""
    manifest = Path(manifest_path)
    out = Path(out_path)
    if not manifest.exists():
        logger.error("manifest not found at %s", manifest)
        return 1

    manifest_data = json.loads(manifest.read_text())
    runs_dir = Path(manifest_data.get("eval_runs_dir", "eval/runs"))
    logger.info("loading labeled runs from %s", runs_dir)
    runs = _load_runs(runs_dir)
    if not runs:
        logger.error(
            "no labeled eval runs found in %s; run `just eval` first to produce them",
            runs_dir,
        )
        return 1

    samples = _build_samples(runs)
    logger.info("fitting calibrator on %d samples", len(samples))
    calibrator = fit_calibrator(samples)
    calibrator.save(out)
    logger.info(
        "calibrator saved: %d per-field maps, %d default samples",
        len(calibrator.maps),
        calibrator.n_samples,
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", nargs="?", default="eval/golden_set/v1/manifest.json")
    parser.add_argument("out", nargs="?", default="./calibration.json")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(main(args.manifest, args.out))
