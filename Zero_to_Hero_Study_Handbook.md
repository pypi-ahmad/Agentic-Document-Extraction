# Paperplane 5: Zero-to-Hero Study Handbook

## Goal

Learn how Paperplane converts selected pages from PDFs, images, and Office files into
context-aware Markdown, grounded evidence, cited organization results, and durable local jobs.

## Run it

Double-click `Paperplane.cmd`, or run:

```powershell
uv run --locked --extra cpu streamlit run workspace_app.py --server.port=8551
```

Open `http://127.0.0.1:8551` and explore Parse, Organize, Jobs, and Benchmarks.
The launcher installs only missing or out-of-date prerequisites; later launches skip setup.

Parse setup stays below navigation in the sidebar. The main workspace uses one document
selector across Input preview, Output, Annotated PDF, Markdown, HTML, and JSON.

## Engine lesson

All engines start off. Select exactly one:

- Docling ADE — local layout, tables, and RapidOCR.
- PDF Inspector ADE — local PDF analysis only.
- Cloud AI ADE — selected cloud vision model.
- Ollama ADE — installed local model that reports vision support.

Cloud enhancement can follow Docling, PDF Inspector, or Ollama. There is no automatic
routing. Agnes accepts private visual inputs as inline PNG data URLs. Its structured output
is schema- and geometry-validated with one bounded correction attempt before failure.

## Contract lesson

`contracts.py` contains the internal grounded response. `ade_contracts.py` exports a strict
ADE v2-style hierarchy with inline grounding and zero-based response-local IDs. The
Paperplane v5 wrapper adds provenance, observed words, confidence state, relations, and
warnings.

Ranges are half-open Unicode offsets. Boxes are normalized top-left coordinates. Atomic
line grounding is authoritative; word boxes appear only when native PDF or RapidOCR words
exactly align. Never infer missing geometry.

## Context lesson

Up to six files run concurrently, but every file is isolated. Earlier selected pages can
guide later selected AI pages. Pages outside the chosen range are never inspected.
`document_intelligence.py` records conservative section, repeated-label, continued-table,
and selection-boundary relationships.

## Workflow lesson

Organize provides cited Classify, Split, and Section results, including explicit
deterministic partials when the local workflow cannot establish stronger semantics.

## Export lesson

Each successful document can download Markdown, sanitized standalone HTML, annotated PDF,
Paperplane JSON, and ADE v2 JSON. The batch ZIP groups available outputs in sanitized,
numbered folders and records every success/failure in `manifest.json`; it intentionally
does not duplicate original uploads. `paperplane/outputs.py` owns this boundary.

## Job lesson

`jobs.py` stores lifecycle metadata in SQLite and private sources/artifacts under
`%LOCALAPPDATA%\Paperplane`. The TTL is seven days. Checkpoints are atomic, interrupted jobs
are discoverable, and users can cancel state or delete retained data. There is no HTTP API
in v5.

## Confidence and benchmark lesson

Raw confidence is not calibrated confidence. A calibration profile must match engine,
model, version, and corpus hash. The locked benchmark manifest names every input, engine,
and metric. Missing runs remain missing; Paperplane does not inherit LandingAI's DocVQA
score or claim parity.

## Code-reading order

1. `workspace_app.py` and `app_pages/`
2. `paperplane/runtime.py`
3. `paperplane/parser.py`
4. `paperplane/contracts.py` and `ade_contracts.py`
5. `paperplane/ade_workflows.py`
6. `paperplane/jobs.py`
7. `document_intelligence.py`, `calibration.py`, `benchmark.py`
8. tests matching each module

## Verification

```powershell
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
uv run python scripts/benchmark_report.py
```
