# Quality, grounding, and benchmarks

Paperplane validates structure and evidence independently of model fluency.

## Runtime safeguards

- Strict provider JSON Schema where supported, followed by Pydantic validation.
- Exact Unicode range validation, normalized box validation, ordered hierarchy, and table
  coordinates.
- Bounded reconciliation/crop verification, duplicate suppression, critical-token checks,
  and isolated per-file/artifact failure.
- Native-PDF words and RapidOCR word boxes are emitted only after exact Markdown alignment;
  no synthetic word geometry.
- Later selected AI pages receive bounded earlier-page context. Files never share context,
  and pages outside a chosen range are not inspected.
- Classify, Split, and Section local results identify deterministic partials.
- HTML output is allowlist-sanitized; scripts, event handlers, and unsafe URL schemes are
  removed. Batch ZIP names are leaf-only, device-safe, and traversal-safe. The app binds to
  localhost with XSRF protection.

## Confidence

Raw confidence may combine OCR score, engine agreement, geometric alignment, and contract
validation. A value is labeled **calibrated** only when engine, model, version, and the
checked-in calibration corpus hash match. Arbitrary Ollama models show raw uncalibrated
confidence and an empty calibrated value.

## Benchmark policy

`benchmarks/manifest.json` pins corpus SHA-256 values, engine names, and metrics: character
and word accuracy, pairwise reading order, TEDS/cell accuracy, continuation F1, grounding
IoU/recall, citation validity, workflow F1, ECE/Brier, latency, tokens, and
cost. A publishable run must include raw outputs, prompts, versions, failures, pricing, and
calibration provenance.

The initial corpus is too small for an accuracy claim. Paperplane does not reuse
LandingAI's DPT-2 DocVQA result or claim ADE accuracy parity.

## Verification

```powershell
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run ruff format --check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
uv run python scripts/benchmark_report.py
```
