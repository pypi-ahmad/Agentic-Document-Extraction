"""Benchmark transparency workspace."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from paperplane.benchmark import BenchmarkManifest, sha256_file

st.title("Benchmarks")
st.caption(
    "Version-pinned evaluation assets and metrics. Missing results are never replaced by claims."
)

manifest_path = Path("benchmarks/manifest.json")
if not manifest_path.exists():
    st.warning("No benchmark manifest is installed.")
    st.stop()

manifest = BenchmarkManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
st.metric("Corpus version", manifest.version)
st.write("**Engines**", ", ".join(manifest.engines))
st.write("**Metrics**", ", ".join(manifest.metrics))

rows = []
for document in manifest.documents:
    path = Path(document.path)
    actual = sha256_file(path) if path.exists() else None
    rows.append(
        {
            "Document": document.id,
            "Tags": ", ".join(document.tags),
            "License": document.license,
            "Available": path.exists(),
            "Hash verified": actual == document.sha256 if actual else False,
        }
    )
st.dataframe(rows, hide_index=True)

results_path = Path("benchmarks/results/latest.json")
if results_path.exists():
    st.json(json.loads(results_path.read_text(encoding="utf-8")), expanded=2)
else:
    st.info(
        "No measured result bundle has been published for this checkout. Run the locked "
        "benchmark workflow before making accuracy or parity claims."
    )
