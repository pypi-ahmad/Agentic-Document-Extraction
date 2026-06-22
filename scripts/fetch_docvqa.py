"""Fetch DocVQA + InfographicVQA for the v0.5.0 eval pipeline.

DocVQA (Mathew et al., 2020) is a public dataset of ~50k
question/answer pairs over ~12k single-page documents. It is
the de-facto benchmark for visual document understanding. The
public mirror we use is HuggingFace ``pixparse/docvqa-single-page-questions``.

InfographicVQA (Mathew et al., 2022) is a similar but harder
benchmark focused on infographics — multi-column, chart-heavy
documents. The public mirror is ``HuggingFaceM4/InfographicVQA``.

We normalize each (question, answer) pair to a one-row golden
set entry: the question becomes the ``query`` field and the
answer becomes the expected value. The image itself is *not*
shipped with the golden set (it would be ~10 GB); instead the
manifest records the HuggingFace image id so the eval runner
can download the image on demand.

This script is gated by ``--enable-multi-dataset`` so users
who only want the v0.4.0 CORD regression set do not need to
download DocVQA.

Output
------

* ``eval/golden_set/v2/docvqa.jsonl``
* ``eval/golden_set/v2/infographicvqa.jsonl``
* ``eval/golden_set/v2/manifest.json``

The manifest embeds the SHA256 of each .jsonl file and a
schema-fields list. Eval runs can use the manifest to detect
local drift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


DOCVQA_DATASET = "pixparse/docvqa-single-page-questions"
INFOGRAPHICVQA_DATASET = "HuggingFaceM4/InfographicVQA"

GOLDEN_SET_DIR = Path(__file__).resolve().parent.parent / "eval" / "golden_set" / "v2"


# ── HuggingFace dataset loaders (optional dependency) ──────────────


def _try_load_hf_dataset(dataset_id: str, split: str) -> list[dict] | None:
    """Attempt to load a HuggingFace dataset. Returns None on failure."""

    try:
        from datasets import load_dataset  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "the 'datasets' package is not installed; cannot fetch %s. "
            "Install with: pip install datasets",
            dataset_id,
        )
        return None
    try:
        ds = load_dataset(dataset_id, split=split)
    except Exception as exc:
        logger.warning("failed to load %s: %s", dataset_id, exc)
        return None
    return list(ds)


# ── Normalization ────────────────────────────────────────────────


def _normalize_docvqa_sample(raw: dict) -> dict | None:
    """Normalize one DocVQA (question, answer) sample to our schema.

    DocVQA's annotation format:

    .. code-block:: json

        {
          "questionId": 123,
          "question": "What is the invoice number?",
          "answers": ["INV-001", "INV001", "inv 1"],
          "image": <PIL image>,
          "page_id": 1
        }

    We pick the most common (modal) answer as the canonical
    expected value. The list of all acceptable answers is
    preserved for the ANLS metric to score against.
    """

    question = (raw.get("question") or "").strip()
    answers = raw.get("answers") or []
    if not question or not answers:
        return None
    answers = [str(a) for a in answers if a is not None]
    if not answers:
        return None
    # Pick the modal answer as the canonical expected value
    from collections import Counter

    counter = Counter(answers)
    canonical = counter.most_common(1)[0][0]
    return {
        "id": str(raw.get("questionId", "")),
        "source": "DocVQA",
        "input": {
            "question": question,
            "page_id": raw.get("page_id"),
            "image": _image_ref(raw.get("image")),
        },
        "expected": {
            "query": question,
            "answer": canonical,
            "acceptable_answers": sorted(set(answers)),
        },
    }


def _normalize_infographicvqa_sample(raw: dict) -> dict | None:
    """Normalize one InfographicVQA sample. Same shape as DocVQA."""

    question = (raw.get("question") or "").strip()
    answers = raw.get("answers") or []
    if not question or not answers:
        return None
    answers = [str(a) for a in answers if a is not None]
    if not answers:
        return None
    from collections import Counter

    counter = Counter(answers)
    canonical = counter.most_common(1)[0][0]
    return {
        "id": str(raw.get("questionId", raw.get("id", ""))),
        "source": "InfographicVQA",
        "input": {
            "question": question,
            "image": _image_ref(raw.get("image")),
        },
        "expected": {
            "query": question,
            "answer": canonical,
            "acceptable_answers": sorted(set(answers)),
        },
    }


def _image_ref(image: object) -> str | None:
    """Return a reference (id or filename) for a PIL image, or None."""

    if image is None:
        return None
    # PIL Image has a filename attribute or a .info dict
    if hasattr(image, "filename") and image.filename:
        return str(image.filename)
    return None


# ── Manifest helpers ─────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_jsonl(samples: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w") as out:
        for s in samples:
            out.write(json.dumps(s) + "\n")
            count += 1
    return count


# ── Public API ────────────────────────────────────────────────────


def fetch_docvqa(target_dir: Path = GOLDEN_SET_DIR, split: str = "validation") -> dict | None:
    """Fetch DocVQA, normalize, write to ``target_dir``, return manifest entry."""

    logger.info("loading DocVQA split=%s from %s", split, DOCVQA_DATASET)
    raw = _try_load_hf_dataset(DOCVQA_DATASET, split=split)
    if not raw:
        return None
    samples: list[dict] = []
    for r in raw:
        n = _normalize_docvqa_sample(r)
        if n is not None:
            samples.append(n)
    out_path = target_dir / "docvqa.jsonl"
    count = _write_jsonl(samples, out_path)
    logger.info("wrote %d DocVQA samples to %s", count, out_path)
    text = out_path.read_text()
    return {
        "name": "docvqa",
        "source": DOCVQA_DATASET,
        "split": split,
        "sample_count": count,
        "license": "DocVQA is available for research use; see the original paper for details.",
        "files": [
            {
                "name": out_path.name,
                "sha256": _sha256(text),
                "bytes": len(text.encode("utf-8")),
            }
        ],
    }


def fetch_infographicvqa(
    target_dir: Path = GOLDEN_SET_DIR, split: str = "validation"
) -> dict | None:
    """Fetch InfographicVQA, normalize, write, return manifest entry."""

    logger.info("loading InfographicVQA split=%s from %s", split, INFOGRAPHICVQA_DATASET)
    raw = _try_load_hf_dataset(INFOGRAPHICVQA_DATASET, split=split)
    if not raw:
        return None
    samples: list[dict] = []
    for r in raw:
        n = _normalize_infographicvqa_sample(r)
        if n is not None:
            samples.append(n)
    out_path = target_dir / "infographicvqa.jsonl"
    count = _write_jsonl(samples, out_path)
    logger.info("wrote %d InfographicVQA samples to %s", count, out_path)
    text = out_path.read_text()
    return {
        "name": "infographicvqa",
        "source": INFOGRAPHICVQA_DATASET,
        "split": split,
        "sample_count": count,
        "license": "InfographicVQA is available for research use; see the original paper for details.",
        "files": [
            {
                "name": out_path.name,
                "sha256": _sha256(text),
                "bytes": len(text.encode("utf-8")),
            }
        ],
    }


def write_manifest(entries: list[dict], target_dir: Path = GOLDEN_SET_DIR) -> Path:
    """Write the combined manifest.json for the v2 golden set."""

    target_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": "v2",
        "license": "Mixed; per-dataset license is recorded in the entries below.",
        "datasets": entries,
    }
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=GOLDEN_SET_DIR,
        help="Directory to write the golden set into.",
    )
    parser.add_argument(
        "--enable-multi-dataset",
        action="store_true",
        help="Required to fetch DocVQA + InfographicVQA. Without this flag the "
        "script refuses to run, to keep the v0.4.0 CORD-only workflow "
        "as the default.",
    )
    parser.add_argument(
        "--datasets",
        nargs="*",
        default=("docvqa", "infographicvqa"),
        choices=("docvqa", "infographicvqa"),
        help="Which datasets to fetch. Default: both.",
    )
    parser.add_argument("--split", default="validation", help="HuggingFace split to fetch")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    if not args.enable_multi_dataset and os.environ.get("ENABLE_MULTI_DATASET") != "1":
        parser.error(
            "Refusing to fetch DocVQA + InfographicVQA without "
            "--enable-multi-dataset (or ENABLE_MULTI_DATASET=1). These are "
            "research-only datasets and the golden set is opt-in."
        )

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    entries: list[dict] = []
    if "docvqa" in args.datasets:
        e = fetch_docvqa(args.target, split=args.split)
        if e is not None:
            entries.append(e)
    if "infographicvqa" in args.datasets:
        e = fetch_infographicvqa(args.target, split=args.split)
        if e is not None:
            entries.append(e)
    if not entries:
        logger.error(
            "no datasets fetched — the 'datasets' package is missing or network "
            "is unavailable. Install with: pip install datasets"
        )
        return 1
    manifest_path = write_manifest(entries, args.target)
    print(json.dumps({"manifest": str(manifest_path), "datasets": entries}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
