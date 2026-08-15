# Release notes

## Unreleased

- Preserved uploads, Parse outputs, Organize values, tabs, and selections across workspace
  navigation within one browser session.
- Replaced the Benchmarks UI page with a Cost page that aggregates input, cached-input,
  output tokens, and configured estimates by model plus a session total.
- Preserved separate local Ollama and cloud-enhancement usage attribution. Free and local
  models contribute tokens at $0 API cost.

## Paperplane 5.2.0

- Replaced whole-page JSON generation for GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR with
  CPU PP-DocLayoutV3 region detection and family-native Ollama crop recognition.
- Added detector-box candidate grounding, vertical marginal-text rotation, repeated-tail
  cleanup, bounded crop output, and partial-page tolerance for empty OCR regions.
- Added automatic PP-DocLayoutV3 checking and download to both launchers.
- Added one bounded DeepSeek retry for empty and transiently failed text regions, partial
  page warnings for isolated failures, and an abort after three consecutive failures.
- Replaced Gemini 3.6 Flash with Gemini 3.7 Flash at the supplied $0.75/$3.75 promotional
  rate and made `GOOGLE_API_KEY` canonical with legacy `GEMINI_API_KEY` fallback.

## Paperplane 5.1.1

- Requested Agnes structured extraction through schema-shaped tool calls while accepting
  its validated JSON content response so bounding boxes reliably reach annotated PDFs.
- Added local JSON Schema and geometry validation with one bounded correction attempt for
  missing, out-of-range, or reversed coordinates.
- Normalized Agnes's equivalent 0–1000 boxes and omitted nullable chunk fields before strict
  validation, with precise validation reasons in launcher logs when correction still fails.
- Preserved private inline PNG input and included all retry tokens in usage reporting.

## Paperplane 5.1.0

- Added executable `Paperplane.sh` for idempotent Linux setup and launch.
- Added Ubuntu/Debian LibreOffice installation, NVIDIA detection with CPU fallback, locked
  uv/Python synchronization, local model checks, and Streamlit startup on
  `127.0.0.1:8551`.
- Added Linux launcher validation to Ubuntu CI and documented supported Linux behavior.

## Paperplane 5.0.3

- Expanded the README with detailed explanations of every processing engine, quality mode,
  cloud model path, grounding feature, workspace view, workflow, job control, benchmark,
  and calibration behavior.
- Shipped and documented the red-and-black dark Streamlit theme.

## Paperplane 5.0.2

- Synchronized setup, capabilities, architecture, deployment, runtime, model, and handbook
  documentation with Agnes 2.5 Flash private visual processing.
- Updated current-version documentation and generated HTML/PDF artifacts to 5.0.2.
- Added a red-and-black dark Streamlit theme with near-black surfaces, charcoal panels,
  red controls, and dark-red borders.

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
