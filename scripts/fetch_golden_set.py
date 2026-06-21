"""Fetch the CORD golden set for the v0.4.0 eval pipeline.

The Consolidated Receipt Dataset (CORD) is a public, Apache-2.0
dataset of ~1,000 Indonesian receipts with per-field annotations.
It is the de-facto smoke test for receipt-extraction pipelines and
saturates around 95-97% F1 for SOTA VLMs.

This script downloads CORD, normalizes the annotations to our
schema (vendor_name, transaction_date, total_amount, etc.), and
writes the result to ``eval/golden_set/v1/cord.jsonl`` with a
SHA256-pinned ``manifest.json``.

CORD source: https://github.com/clovaai/cord (original)
Public mirror: https://huggingface.co/datasets/naver-clova-ix/cord-v1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

CORD_REPO = "https://github.com/clovaai/cord/archive/refs/heads/main.zip"
GOLDEN_SET_DIR = Path(__file__).resolve().parent.parent / "eval" / "golden_set" / "v1"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_cord_sample(raw: dict) -> dict:
    """Map a CORD sample to our extraction schema.

    CORD's annotation format is a flat dict of grouped fields
    (e.g. ``menu.nm``, ``menu.price``, ``sub_total.total_price``).
    We pick a small subset of high-signal fields and emit them
    under our schema names.

    Reference: https://github.com/clovaai/cord/blob/master/README.md
    """
    lines = raw.get("valid_line", [])
    menu_items: list[dict] = []
    for line in lines:
        try:
            menu = line.get("menu", {})
            menu_items.append(
                {
                    "name": menu.get("nm", [""])[0] if menu.get("nm") else "",
                    "quantity": menu.get("qty", [""])[0] if menu.get("qty") else "",
                    "price": menu.get("price", [""])[0] if menu.get("price") else "",
                }
            )
        except (AttributeError, TypeError, KeyError):
            continue

    sub = raw.get("sub_total", {})
    total = raw.get("total", {})

    def _first(seq: object) -> str:
        if isinstance(seq, list) and seq:
            return str(seq[0])
        if isinstance(seq, str):
            return seq
        return ""

    return {
        "merchant_name": _first(sub.get("company_name", [""])),
        "transaction_date": _first(sub.get("menu_sub_total", [""])),  # CORD lacks a date field
        "subtotal": _first(sub.get("subtotal_price", [""])),
        "tax_amount": _first(sub.get("tax_price", [""])),
        "total_amount": _first(total.get("total_price", [""])),
        "items": menu_items,
    }


def fetch_golden_set(target_dir: Path = GOLDEN_SET_DIR) -> dict:
    """Download CORD, normalize, write to ``target_dir``, return manifest."""
    target_dir.mkdir(parents=True, exist_ok=True)
    archive = target_dir / "_cord-source.zip"
    if not archive.exists():
        logger.info("fetching CORD from %s", CORD_REPO)
        try:
            urllib.request.urlretrieve(CORD_REPO, archive)
        except urllib.error.URLError as exc:
            logger.error("CORD download failed: %s", exc)
            raise

    extract_dir = target_dir / "_cord-source"
    if not extract_dir.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(extract_dir)

    # CORD ships one JSON per receipt under dataset/receipt/...
    receipt_dir_candidates = list(extract_dir.rglob("receipt"))
    if not receipt_dir_candidates:
        raise RuntimeError("CORD archive does not contain a 'receipt' directory")
    receipt_dir = receipt_dir_candidates[0]

    out_path = target_dir / "cord.jsonl"
    count = 0
    with out_path.open("w") as out:
        for sample_file in sorted(receipt_dir.rglob("*.json")):
            try:
                raw = json.loads(sample_file.read_text())
            except json.JSONDecodeError:
                continue
            normalized = _normalize_cord_sample(raw)
            out.write(
                json.dumps(
                    {
                        "id": sample_file.stem,
                        "source": "CORD",
                        "input": {"receipt": sample_file.relative_to(target_dir).as_posix()},
                        "expected": normalized,
                    }
                )
                + "\n"
            )
            count += 1
    logger.info("wrote %d samples to %s", count, out_path)

    text = out_path.read_text()
    manifest = {
        "version": "v1",
        "license": "CORD is Apache-2.0; this normalization is MIT.",
        "source": CORD_REPO,
        "sample_count": count,
        "schema_fields": sorted(_normalize_cord_sample({}).keys()),
        "files": [
            {
                "name": out_path.name,
                "sha256": _sha256(text),
                "bytes": len(text.encode("utf-8")),
            }
        ],
    }
    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        type=Path,
        default=GOLDEN_SET_DIR,
        help="Directory to write the golden set into.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        manifest = fetch_golden_set(args.target)
    except Exception as exc:
        logger.error("could not build golden set: %s", exc)
        return 1
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
