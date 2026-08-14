"""Validate the locked benchmark manifest and build a transparent Pages artifact."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from paperplane.benchmark import BenchmarkManifest, sha256_file  # noqa: E402


def main() -> None:
    manifest_path = ROOT / "benchmarks" / "manifest.json"
    manifest = BenchmarkManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    rows = []
    valid = True
    for document in manifest.documents:
        path = ROOT / document.path
        actual = sha256_file(path) if path.exists() else None
        verified = actual == document.sha256
        valid &= verified
        rows.append(
            f"<tr><td>{html.escape(document.id)}</td><td>{path.exists()}</td>"
            f"<td>{verified}</td><td><code>{html.escape(document.sha256)}</code></td></tr>"
        )
    output = ROOT / "benchmark-site"
    output.mkdir(exist_ok=True)
    result_path = ROOT / "benchmarks" / "results" / "latest.json"
    result_html = (
        f"<pre>{html.escape(result_path.read_text(encoding='utf-8'))}</pre>"
        if result_path.exists()
        else "<p>No measured result bundle is published for this revision.</p>"
    )
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Paperplane benchmarks</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:3rem auto;padding:0 1rem}}table{{border-collapse:collapse}}td,th{{border:1px solid #bbb;padding:.5rem;text-align:left}}code{{font-size:.8rem}}</style>
</head><body><h1>Paperplane benchmark transparency report</h1>
<p>Corpus: <strong>{html.escape(manifest.version)}</strong>. This page reports integrity separately
from measured quality. It makes no LandingAI accuracy-parity claim.</p>
<h2>Corpus integrity</h2><table><thead><tr><th>Document</th><th>Available</th><th>Hash verified</th><th>Expected SHA-256</th></tr></thead><tbody>{"".join(rows)}</tbody></table>
<h2>Measured results</h2>{result_html}
<h2>Manifest</h2><pre>{html.escape(json.dumps(manifest.model_dump(mode="json"), indent=2))}</pre>
</body></html>"""
    (output / "index.html").write_text(page, encoding="utf-8")
    if not valid:
        raise SystemExit("Benchmark corpus integrity check failed")


if __name__ == "__main__":
    main()
