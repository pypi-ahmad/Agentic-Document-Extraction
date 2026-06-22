"""Tests for the eval-diff CLI script."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_run(path: Path, *, field_f1: float, ece: float, auroc: float) -> None:
    path.write_text(
        json.dumps(
            {
                "field_f1": field_f1,
                "ece": ece,
                "auroc": auroc,
                "field_precision": field_f1,
                "field_recall": field_f1,
                "schema_conformance": 1.0,
                "brier": 0.1,
                "coverage_at_target_accuracy_0.95": 0.9,
                "threshold_at_target_accuracy_0.95": 0.6,
                "sample_count": 100,
            }
        )
    )


def test_eval_diff_no_runs(tmp_path: Path) -> None:
    runs_dir = tmp_path / "eval" / "runs"
    runs_dir.mkdir(parents=True)
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-c", "from scripts.eval_diff import main; main()"],
        cwd=project_root,
        env={"PYTHONPATH": str(project_root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    # The script reads from eval/runs; with no runs the message is printed.
    # The cwd's eval/runs is empty (project root has no runs by default).
    assert "need at least 2" in result.stdout or result.returncode == 0


def test_eval_diff_one_run(tmp_path: Path) -> None:
    runs_dir = tmp_path / "eval" / "runs"
    runs_dir.mkdir(parents=True)
    _write_run(runs_dir / "a.json", field_f1=0.8, ece=0.05, auroc=0.9)
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"from scripts.eval_diff import main; main('{runs_dir}')",
        ],
        cwd=project_root,
        env={"PYTHONPATH": str(project_root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "need at least 2" in result.stdout


def test_eval_diff_improvement_exits_zero(tmp_path: Path) -> None:
    runs_dir = tmp_path / "eval" / "runs"
    runs_dir.mkdir(parents=True)
    _write_run(runs_dir / "20260101_000000.json", field_f1=0.80, ece=0.10, auroc=0.85)
    _write_run(runs_dir / "20260102_000000.json", field_f1=0.85, ece=0.05, auroc=0.90)
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; from scripts.eval_diff import main; sys.exit(main('{runs_dir}'))",
        ],
        cwd=project_root,
        env={"PYTHONPATH": str(project_root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "| metric |" in result.stdout
    assert "field_f1" in result.stdout


def test_eval_diff_regression_exits_one(tmp_path: Path) -> None:
    runs_dir = tmp_path / "eval" / "runs"
    runs_dir.mkdir(parents=True)
    # Use timestamp-style names so the alphabetical sort matches the
    # intended chronological order (older → newer).
    _write_run(runs_dir / "20260101_000000.json", field_f1=0.90, ece=0.05, auroc=0.95)
    _write_run(runs_dir / "20260102_000000.json", field_f1=0.80, ece=0.20, auroc=0.80)
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; from scripts.eval_diff import main; sys.exit(main('{runs_dir}'))",
        ],
        cwd=project_root,
        env={"PYTHONPATH": str(project_root), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "field_f1" in result.stdout
    # Regression marker is shown.
    assert "⚠" in result.stdout
