# Paperplane contributor onboarding

Paperplane 5 is an open-source, local-first, multipage Streamlit document-intelligence
workspace. It produces
reading-order Markdown, annotated evidence, strict ADE v2-style JSON, a richer Paperplane
v5 contract, and cited Classify/Split/Section results.

Forks, local modifications, and pull requests are welcome under the MIT License. Submitted
fixtures must be synthetic, redacted, or redistributable; contributors are responsible for
the data and credentials used on their own machines.

## Start

```powershell
uv sync --locked --extra cpu --extra test --extra lint --extra docs
uv run --locked --extra cpu python -m paperplane.model_store --prepare
uv run --extra cpu streamlit run workspace_app.py --server.port=8551
```

Windows users can double-click `Paperplane.cmd`. On the first run it installs any missing
uv, Python 3.12.10, LibreOffice, CPU/CUDA dependencies, and the permanent versioned
Docling/RapidOCR/PP-DocLayoutV3 model set. Later runs verify the locked environment,
manifest, and file sizes, then launch directly on port 8551. Ollama manages its own models
separately.

Credentials come from Windows user/process variables, ignored `.env`, or Streamlit
secrets. `OLLAMA_BASE_URL` defaults to `http://127.0.0.1:11434`. Never log or commit keys.

## Mental model

```text
workspace_app navigation
  -> Parse sidebar: explicit engine + uploads + per-file ranges
  -> full-width shared-document tabs: input/output/PDF/Markdown/HTML/JSON
  -> grounded internal ParseResponse
  -> strict ADE v2 / Paperplane v5 / annotated PDF / sanitized HTML / batch ZIP
  -> Organize cited workflows
  -> SQLite job metadata + private artifacts (7-day TTL)
```

Files never share context. Earlier selected pages can inform later selected pages; pages
outside the range are never inspected. Missing word boxes/citations/calibration remain
missing. Local workflows return warnings/partials instead of silently calling cloud AI.

## Repository map

| Path | Purpose |
|---|---|
| `workspace_app.py` | Multipage navigation |
| `streamlit_app.py` | Parse page |
| `app_pages/` | Organize, Jobs, Cost |
| `paperplane/runtime.py` | Concurrent batch/provider composition |
| `paperplane/parser.py` | Page-range and cross-page orchestration |
| `paperplane/model_store.py` | Permanent versioned local model weights |
| `paperplane/ade_contracts.py` | Engine options and public exports |
| `paperplane/ade_workflows.py` | Classify/Split/Section |
| `paperplane/jobs.py` | SQLite lifecycle/checkpoints/artifacts |
| `paperplane/ollama_document.py` | Model discovery and vision/cloud chain |
| `paperplane/document_intelligence.py` | Section/table/boundary relationships |
| `paperplane/calibration.py` | Profile-pinned confidence |
| `paperplane/benchmark.py` | Manifests and metrics |
| `paperplane/outputs.py` | Sanitized standalone HTML and traversal-safe batch bundles |

## Rules

- Keep Streamlit out of core modules.
- Keep four engine choices explicit and mutually exclusive.
- Preserve exact Unicode ranges and normalized coordinates.
- Never fabricate a word box, citation, calibrated score, or benchmark result.
- Do not add an HTTP API without a separate approved design.
- Update README, active docs, changelog, release notes, and generated guides after code.

## Checks

```powershell
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run ruff format --check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
uv run python scripts/build_app_guide.py
uv run python scripts/build_handbook.py
```
