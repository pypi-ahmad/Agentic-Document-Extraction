# Release notes

## Paperplane 5.0.1

- Agnes 2.5 Flash now supports private visual Parse and enhancement through inline image
  input; uploaded images do not need public URLs.

## Paperplane 5.0.0

Paperplane 5 is an ADE-inspired, private document-intelligence workspace with explicit
engines, grounded contracts, cited workflows, and durable local jobs.

## Highlights

- Multipage Streamlit UI: Parse, Organize, Jobs, Benchmarks.
- Four exclusive engine toggles, all off initially: Docling, PDF Inspector, Cloud AI, and
  Ollama; optional cloud enhancement for local engines.
- Installed Ollama model discovery and live vision-capability checks.
- Strict ADE v2-style Parse export plus namespaced Paperplane v5 JSON.
- Cross-page selected-document context, section/repeated-label/continued-table relations,
  exact native/RapidOCR word grounding, and explicit calibration state.
- Deterministic cited Classify, Split, and Section workflows.
- Vertical Parse controls below sidebar navigation, one shared-document selector, and
  full-width Input preview, Output, Annotated PDF, Markdown, HTML, and JSON tabs.
- Selected-document downloads plus a traversal-safe whole-batch ZIP with a versioned
  success/failure manifest and no duplicated source uploads.
- SQLite jobs, checkpoints, seven-day private artifact retention, cancellation state, and
  deletion controls.
- Locked benchmark manifest, metric helpers, and GitHub Pages transparency workflow with
  no fabricated or inherited accuracy claims.
- Agnes remains $0 in configured cost estimates; private visual use was blocked in this
  release because only public image URLs were supported.

There is no HTTP API in this release. “ADE compatible” refers to versioned data contracts
and job semantics, not LandingAI client or model parity.
