"""Tests for the DocVQA / InfographicVQA fetcher.

We cannot depend on the actual HuggingFace datasets being
downloadable in CI, so these tests focus on:

* normalization of the (question, answers) format
* the manifest schema
* the opt-in safety (the script refuses to run without
  --enable-multi-dataset)
* the empty / no-data fallbacks
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import fetch_docvqa

# ── Normalization ────────────────────────────────────────────────


def test_normalize_docvqa_basic() -> None:
    raw = {
        "questionId": 1,
        "question": "What is the invoice number?",
        "answers": ["INV-001", "INV001", "INV-001"],
        "image": None,
        "page_id": 1,
    }
    out = fetch_docvqa._normalize_docvqa_sample(raw)
    assert out is not None
    assert out["id"] == "1"
    assert out["source"] == "DocVQA"
    assert out["expected"]["query"] == "What is the invoice number?"
    assert out["expected"]["answer"] == "INV-001"  # modal
    assert out["expected"]["acceptable_answers"] == ["INV-001", "INV001"]


def test_normalize_docvqa_no_question() -> None:
    raw = {"questionId": 1, "question": "", "answers": ["x"]}
    assert fetch_docvqa._normalize_docvqa_sample(raw) is None


def test_normalize_docvqa_no_answers() -> None:
    raw = {"questionId": 1, "question": "Q?", "answers": []}
    assert fetch_docvqa._normalize_docvqa_sample(raw) is None


def test_normalize_docvqa_filters_null_answers() -> None:
    raw = {
        "questionId": 1,
        "question": "Q?",
        "answers": ["x", None, "y", "x"],
    }
    out = fetch_docvqa._normalize_docvqa_sample(raw)
    assert out is not None
    assert out["expected"]["answer"] == "x"
    assert out["expected"]["acceptable_answers"] == ["x", "y"]


def test_normalize_infographicvqa_basic() -> None:
    raw = {
        "questionId": 42,
        "question": "What is the title?",
        "answers": ["Title A", "Title A", "title a"],
    }
    out = fetch_docvqa._normalize_infographicvqa_sample(raw)
    assert out is not None
    assert out["id"] == "42"
    assert out["source"] == "InfographicVQA"
    assert out["expected"]["answer"] == "Title A"


def test_normalize_infographicvqa_no_question() -> None:
    raw = {"question": "", "answers": ["x"]}
    assert fetch_docvqa._normalize_infographicvqa_sample(raw) is None


# ── Image ref helper ─────────────────────────────────────────────


def test_image_ref_none() -> None:
    assert fetch_docvqa._image_ref(None) is None


def test_image_ref_with_filename() -> None:
    class _Img:
        filename = "/tmp/x.png"

    assert fetch_docvqa._image_ref(_Img()) == "/tmp/x.png"


# ── Manifest helpers ─────────────────────────────────────────────


def test_write_manifest(tmp_path: Path) -> None:
    entries = [
        {
            "name": "docvqa",
            "source": "x",
            "split": "validation",
            "sample_count": 10,
            "license": "research",
            "files": [
                {
                    "name": "docvqa.jsonl",
                    "sha256": "abc",
                    "bytes": 100,
                }
            ],
        }
    ]
    path = fetch_docvqa.write_manifest(entries, tmp_path)
    assert path == tmp_path / "manifest.json"
    payload = json.loads(path.read_text())
    assert payload["version"] == "v2"
    assert len(payload["datasets"]) == 1
    assert payload["datasets"][0]["sample_count"] == 10


def test_write_jsonl(tmp_path: Path) -> None:
    samples = [
        {"id": "1", "expected": {"answer": "x"}},
        {"id": "2", "expected": {"answer": "y"}},
    ]
    path = tmp_path / "samples.jsonl"
    count = fetch_docvqa._write_jsonl(samples, path)
    assert count == 2
    lines = path.read_text().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "1"


# ── Opt-in safety ────────────────────────────────────────────────


def test_main_refuses_without_flag(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc:
        fetch_docvqa.main([])
    assert exc.value.code == 2  # argparse error
    captured = capsys.readouterr()
    assert "Refusing to fetch" in captured.err or "Refusing to fetch" in captured.stdout


def test_main_refuses_without_flag_env(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.delenv("ENABLE_MULTI_DATASET", raising=False)
    with pytest.raises(SystemExit) as exc:
        fetch_docvqa.main([])
    assert exc.value.code == 2


def test_main_runs_with_flag_but_no_datasets_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the flag is set but datasets is missing, the script
    exits 1 with a clear error."""

    monkeypatch.setattr(
        sys,
        "modules",
        {k: v for k, v in sys.modules.items() if k != "datasets"},
    )
    # Make `import datasets` fail
    import builtins

    orig_import = builtins.__import__

    def _import(name: str, *args: object, **kwargs: object) -> object:
        if name == "datasets" or name.startswith("datasets."):
            raise ImportError("no datasets")
        return orig_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _import)
    rc = fetch_docvqa.main(["--enable-multi-dataset", "--target", str(tmp_path)])
    assert rc == 1
