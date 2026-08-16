# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

### Changed

### Fixed

## [5.3.1] - 2026-08-17

Documentation corrections: expanded README overview and index, corrected calibration claims, added codebase deep dive and Diataxis guides, refreshed the code knowledge graph.
## [5.3.0] - 2026-08-15

### Added
- Permanent versioned storage for Docling, RapidOCR, and PP-DocLayoutV3 weights with offline migration and fast launch validation.
- Session Cost reporting by model, live parse progress with percentages, and persistent workspace navigation state.
- Community Support and Disclaimer documents, manual smoke-test guidance, and current structured bug reporting.

### Changed
- PDF source and annotated previews now follow the selected or successfully parsed page range.
- Launchers preserve optional development tools and isolate PyTorch's bundled CUDA runtime from incompatible system DLLs.

### Fixed
- Docling cloud enhancement now describes figures and records their token usage without treating local placeholders as failures.
- Gemini structured-output enums, stale Windows launcher replacement, and CUDA/torch repair detection.
## [5.2.0] - 2026-08-15

### Added

- Added live batch progress with document/page status, output-generation status, and a
  monotonic percentage from preparation through completion.

- Added a session Cost page with input, cached-input, output, per-model, and total estimates.

- Added CPU PP-DocLayoutV3 region detection for GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR,
  including automatic launcher setup and detector-box candidate grounding.
- Added Gemini 3.7 Flash with canonical `GOOGLE_API_KEY` support and legacy
  `GEMINI_API_KEY` fallback.

### Changed

- Removed the redundant "Private local workspace" badge from the Parse header.

- Replaced the Benchmarks workspace page with Cost while retaining benchmark tooling and
  checked-in evaluation assets.

- Profiled Ollama OCR models now receive family-native region crops instead of a forced
  whole-page JSON schema; RapidOCR remains only for exact final word-box alignment.
- Updated configured synchronous cost estimates from the supplied model rates, including
  Gemini 3.7 at $0.75/$3.75 per million input/output tokens and Luna cache reads at $0.02.
- Synchronized README, setup, security, model, engine, troubleshooting, and generated
  HTML/PDF documentation.

### Fixed

- Preserved uploads, Parse and Organize state, selections, and outputs across page changes.
- Split Ollama and cloud-enhancement usage by actual model for accurate session estimates.
- Fixed Gemini Cloud AI requests by sending Google's REST-native structured-output MIME
  enum and enforcing each selected model's minimum supported thinking level.

- Prevented repeated GLM Markdown tails, vertical marginal-text failures, empty visual
  responses, and isolated empty OCR crops from aborting or inflating a page result.
- Retried empty or transiently failed DeepSeek regions once, preserved successful sibling
  regions with warnings, bounded sustained failures, and surfaced safe Ollama errors.

## [5.1.1] - 2026-08-15

Fix Agnes annotated-PDF grounding with forced schema tool calls, local geometry validation, and one bounded correction attempt.
## [5.1.0] - 2026-08-15

### Added

- Added an executable one-file Linux launcher, Paperplane.sh, with uv/Python setup, LibreOffice checks, NVIDIA or CPU selection, Docling model preparation, and local Streamlit startup.
- Added Linux launch documentation and CI coverage.

### Fixed

- Made generated handbook PDFs byte-for-byte reproducible.
## [5.0.3] - 2026-08-14

### Changed

- Expanded the README with detailed explanations of every supported engine, quality mode, model path, grounding feature, workspace view, workflow, job control, benchmark, and calibration behavior.
- Shipped and documented the red-and-black dark Streamlit theme.
## [5.0.2] - 2026-08-14

### Changed

- Synchronized all current setup, capabilities, architecture, deployment, runtime, model, and handbook documentation with Agnes 2.5 Flash private visual processing.
- Rebuilt the published HTML and PDF documentation artifacts.
- Replaced the blue accent theme with a native Streamlit red-and-black dark palette.

## [5.0.1] - 2026-08-14

### Fixed

- Enabled Agnes 2.5 Flash private visual Parse and enhancement with inline PNG input, removing the public-image URL restriction.
## [5.0.0] - 2026-08-14

### Added

- Multipage Parse, Extract, Organize, Jobs, and Benchmarks workspace.
- Four exclusive engine toggles with no default selection, Ollama model/capability
  discovery, and optional cloud enhancement after local engines.
- Strict ADE v2-style Parse JSON and namespaced Paperplane v5 JSON.
- Exact native-PDF/RapidOCR word grounding, selected-page cross-page context, conservative
  section/table relations, and profile-pinned confidence calibration.
- Schema builder, fail-closed cited Extract, and cited Classify/Split/Section workflows.
- SQLite job lifecycle, atomic checkpoints, seven-day artifact retention, cancellation
  state, per-job deletion, and clear-all.
- Locked benchmark manifest, metric helpers, and GitHub Pages transparency report.
- Sanitized standalone HTML for every completed Parse result.
- Selected-document Markdown, HTML, annotated PDF, Paperplane JSON, and ADE v2 JSON
  downloads plus a traversal-safe batch ZIP with a versioned success/failure manifest.

### Changed

- Replaced five combined strategy choices with four primary engines plus a separate cloud
  enhancement switch.
- Switched the launcher to `workspace_app.py` while preserving port 8551.
- Blocked Agnes private visual Parse/enhancement because its current image interface
  requires public URLs; text workflows remain available.
- Changed document/result handling from session-only to explicit seven-day local retention.
- `Paperplane.cmd` now verifies the locked environment and local model artifacts, performs
  setup only when something is missing or out of date, and launches Streamlit directly
  from the ready virtual environment.
- Parse setup now lives vertically below sidebar navigation with mutually exclusive engine
  toggles. One shared document selector drives full-width Input preview, Output, Annotated
  PDF, Markdown, HTML, and JSON tabs.
- Python-Markdown is now a runtime dependency; model-produced HTML remains allowlist
  sanitized. Batch bundles omit original uploads and retain partial successes.

### Removed

- The schema-based Extract page, field schema/value workflow, Extract response contract,
  and extraction-specific benchmark metric.

### Fixed

## [4.2.1] - 2026-08-14

### Fixed

- Keep `uv.lock` synchronized and committed whenever the release script changes the project version, so locked installs succeed on clean systems and CI.
## [4.2.0] - 2026-08-14

### Added

- A fixed six-model catalog with Grok 4.6, GPT-5.6 Luna, Gemini 3.5 Flash-Lite, Gemini 3.6
  Flash, Claude Sonnet 5, and Agnes 2.5 Flash using verified production API IDs.
- Provider-native structured-output adapters for xAI Responses, Google Gemini
  `generateContent`, Anthropic Messages, and Agnes Chat Completions.
- Provider-token aggregation and an expandable Streamlit cost estimate using configured
  per-million-token rates.
- Local Docling parsing for native PDFs, DOCX, PPTX, XLSX, ODT, ODP, ODS, and CSV.
- Automatic per-page routing for native, scanned, and mixed PDFs.
- HTML-table output, atomic-line grounding, and explicit semantic-only Office geometry.
- Rendered Output, Annotated PDF, Markdown, and JSON result tabs with downloadable PDF,
  Markdown, and JSON artifacts.
- In-memory source overlays for grounded PDF/image blocks and semantic evidence reports for
  Office content without reliable geometry.

### Changed

- The model selector now uses the same selected model for drafting and any bounded
  verification calls without persisting credentials or documents.
- Gemini Flash 3.7 was corrected to the current official stable `gemini-3.6-flash` API ID.
- AI provider credentials are required only for scanned/image content and optional figure
  descriptions; native documents can be converted locally.
- `Paperplane.cmd` now downloads required Docling layout and table models during setup.
- Docling's Windows layout path runs without Torch compilation or Visual Studio build tools.


### Fixed
## [4.0.0] - 2026-08-14

### Added

- The Windows launcher now bootstraps uv, Python 3.12.10, and locked runtime dependencies
  before starting Streamlit.

- A single local Streamlit workspace with native document preview, processing modes,
  grounded Markdown/JSON inspection, downloads, and AppTest coverage.
- A framework-neutral `paperplane` parsing package and one-file Windows launcher.

### Changed

- Configuration now prefers Windows user environment variables, with ignored `.env` and
  Streamlit secrets available as local fallbacks.

- The UI now calls the parser directly in-process and retains only the current Streamlit
  session state.
- Releases are source-only GitHub releases.

### Removed

- FastAPI, Next.js, React, Node.js, npm, Docker, PyPI publishing, and all REST endpoints.
- Schema extraction, inactive providers, telemetry, authentication middleware, jobs,
  persistence, and legacy pipeline modules.

## [3.0.0] - 2026-08-14

### Added

- A root-level `Paperplane.cmd` launcher for starting both services by double-click and
  opening the verified frontend in the default Windows browser.
- Synchronous grounded Parse and Extract contracts with Fast, Balanced, and Audit modes.
- A focused Next.js workspace for one local upload and its Markdown or JSON response.

### Changed

- Parsing now completes in one `POST /v2/parse` request and returns the document directly.
- The frontend keeps only the current result in memory.
- Deployment now needs only FastAPI, Next.js, and OpenAI access.

### Removed

- Application databases, migrations, background workers, queues, durable jobs, and artifacts.
- Job polling, cancellation, resume, saved schemas, reviews, curation, and run history APIs.
- Database and migration dependencies and the database-only Compose service.

### Security

- Preserved strict upload validation, bounded model work, API-key authentication, CORS
  restrictions, throttling, safe errors, and backend-only provider credentials.
## [2.0.0] - 2026-07-26

### Added

- OpenAI-only V2 pipeline pairing `gpt-5.6-luna` page drafts with bounded
  `gpt-5.6-terra` crop verification.
- Strict grounded document contracts for hierarchy, checkboxes, tables, citations,
  bounding boxes, document splits, schema fields, and explicit abstention.
- Content-addressed page caching, OpenAI prompt-cache accounting, configurable cost
  reporting, PostgreSQL-compatible page-task leases, retries, and idempotent assembly.
- Auditable Markdown, JSON, schema extraction, usage report, and annotated PDF artifacts.
- Economy, Balanced, and Audit modes in a new production extraction workspace.
- WebP ingestion and PostgreSQL/`asyncpg` deployment support.

### Changed

- Replaced the active PaddleOCR/Ollama/provider runtime and legacy parse API with
  `/api/v2/jobs` and server-side OpenAI configuration.
- Reworked setup documentation and Docker Compose around an optional PostgreSQL service;
  local model weights, GPU containers, and Ollama are no longer required.

### Fixed

- Prevented SQLite-only connection options and PRAGMA statements from reaching
  PostgreSQL deployments.
- Prevented failed page tasks from leaving jobs permanently active by retrying three
  times before atomically recording page and job failure.

## [1.0.0] - 2026-07-23

### Added

- Local PDF and scanned-document ingestion with GLM-OCR through Ollama.
- Layout-aware, LLM-ready clean Markdown and grounded Markdown artifacts.
- Durable parse jobs with page checkpoints, progress events, retries, warnings,
  searchable PDFs, grounding PDFs, and downloadable bundles.
- Structured Qwen3.5 vision review with bounded, region-targeted repair.
- Page and region diagnostics, stable bounding-box IDs, context JSON, and figure crops.
- A focused UI for upload, page progress, source/Markdown preview, diagnostics,
  and `.md` download.
- Required annotated PDF output with type-colored region boxes, IDs, and region labels.
- Responsive output gallery for previewing and downloading every public job artifact.

### Changed

- Replaced the legacy hosted-LLM extraction workflow with a local document-
  to-Markdown pipeline.
- Simplified deployment to the FastAPI parser, Next.js UI, SQLite, and Ollama.
- Rebuilt the README and Zero-to-Hero handbook around the v1 architecture.
- Made package publishing an explicit manual action; GitHub releases do not publish to PyPI.
- Artifact responses expose filenames and inline preview URLs while preserving existing
  download URLs and `grounding_pdf` compatibility.

### Fixed

- Resolved the PaddleOCR-VL worker from the repository root and mounted the persistent
  host cache at the image's `/home/paddleocr/.paddlex` model location.

### Removed

- Legacy extraction, schema, review, provider, and MCP product surfaces.

### Migration

- Alembic revision `0005_markdown_parser_reset` drops all legacy extraction tables.
  Back up existing data or start v1 with a new database.

## [0.6.0] - 2026-06-22

### Added

- **MCP server support (stdio).** New `backend/app/mcp_server.py`
  exposes four MCP tools on top of the v0.5.0 extraction stack:
  `extract_document`, `verify_extraction`, `resolve_entities`, and
  `eval_golden_set`.
- **Optional MCP dependency extra.** `pyproject.toml` now ships
  `mcp[cli]>=1.0.0` under `[project.optional-dependencies].mcp` and
  an executable script entry point `ade-mcp`.
- **MCP test suite.** `backend/tests/test_mcp_server.py` adds 47 tests
  for tool schemas, tool behavior, eval scoring paths, and server entrypoint.
- **MCP docs and quick-start paths.** Added `docs/MCP.md` plus README
  MCP quick-start and client config examples.

### Changed

- **Version bump to 0.6.0.** Package/app runtime version updated from
  0.5.0 to 0.6.0.
- **CI now includes MCP coverage.** CI installs the `mcp` extra and
  runs `backend/tests/test_mcp_server.py` before the full backend suite.

## [0.5.0] - 2026-06-22

### Added

- **Layout-aware parsing.** A new `BaseLayoutProvider` ABI returns
  a `LayoutResult` with per-token bbox, region types (paragraph,
  table, form-field, ...), reading order, and table cells. The
  Docling engine ships in layout mode as `docling-layout`. The
  v0.4.0 `OCRResult` is bridged to a layout result via
  `LayoutResult.from_ocr_result` so downstream stages degrade
  gracefully when no spatial metadata is available.
  (`backend/app/services/ocr/layout_base.py`,
  `docling_layout_provider.py`, `layout_registry.py`).
- **Evidence-grounded extraction.** Every field the LLM
  extracts MUST cite the page, bbox, and verbatim text span in
  the document. `Evidence` / `EvidenceMap` reject fields with
  missing or empty text_span and clamp bboxes to [0, 1].
  `prompts/v2/extraction.md` is the new prompt version; v1
  stays for the regression gate.
  (`backend/app/services/extraction/evidence.py`).
- **Independent verifier + conflict resolver.** A small model
  re-checks each field's evidence against the document. Three
  implementations: `NoOpVerifier`, `HeuristicVerifier` (default;
  text_span substring + score threshold), and `LLMVerifier`
  (Ollama). Disputed fields are routed to human review.
  (`backend/app/services/extraction/verifier.py`).
- **Cross-page entity resolver.** Jaccard-similarity-based
  union-find clustering with abbreviation-aware canonical-form
  selection. Handles split-across-lines, repeated table
  headers, "see above" references.
  (`backend/app/services/extraction/cross_page.py`).
- **Schema-aware field strategies.** Per-kind validators +
  post-processors for `string`, `number`, `boolean`, `date`,
  `currency`, `id`, `address`, `table`, `signature`, `list`,
  `object`. Each strategy exposes a `prompt_fragment` for the
  v2 prompt to nudge the LLM toward the right format.
  (`backend/app/services/extraction/field_strategies.py`).
- **Double-pass self-correction.** When `enable_double_pass` is
  True, the reflect node computes a diff between two extraction
  passes and routes disagreed fields to human review.
  Local structural-diff explanation; the v2/reflection prompt
  can replace it with an LLM-generated diff_explanation.
  (`backend/app/services/extraction/double_pass.py`).
- **Composite confidence (calibration v2).** Replaces the v0.4.0
  PAVA-only self-reported confidence with a weighted sum of
  three independent signals: logprob-derived confidence, verifier
  agreement, and evidence coverage. Components that cannot be
  computed are dropped and the remaining weights are
  re-normalized.
  (`backend/app/services/eval/calibration_v2.py`).
- **DocVQA + InfographicVQA golden set.** HuggingFace-backed
  fetcher behind an explicit `--enable-multi-dataset` flag.
  Each (question, answers) pair is normalized to our schema.
  Output: `eval/golden_set/v2/{docvqa,infographicvqa}.jsonl`
  and a per-dataset manifest with sha256 + license.
  (`scripts/fetch_docvqa.py`, `eval/golden_set/v2/manifest.json`).
- **v0.5.0 metric suite.** Replaces and extends the v0.4.0
  metrics with TEDS, cell P/R/F1, row/column structure
  accuracy, header match, exact match, token F1, evidence
  attribution accuracy, bbox IoU, page localization accuracy,
  and end-to-end task success rate. A `run_v2_suite` helper
  takes optional inputs and emits a flat dict.
  (`backend/app/services/eval/metrics_v2.py`).
- **Three new tables** for the v0.5.0 pipeline
  (`extraction_evidence`, `extraction_entities`,
  `extraction_verifier_runs`) and Alembic migration
  `0004_evidence_entities_verifier`.
- **Four new settings** on `Settings`: `enable_layout_parsing`,
  `enable_verifier`, `enable_double_pass`,
  `enable_cross_page_entities`. All default to `True` in
  v0.5.0; setting any to `False` falls back to the v0.4.0
  behaviour for that stage.

### Migration

- New tables on `extractions` and per-field evidence; Alembic
  migration `0004_evidence_entities_verifier`. Existing
  v0.4.0 extractions are unaffected; new extractions get
  rows in the new tables.
- Prompts: `prompts/v1/*` is unchanged and remains the
  regression gate. `prompts/v2/*` is the new evidence-grounded
  prompt set.
- Calibration: the v0.4.0 `FieldCalibrator` JSON artifact is
  loaded as v0.5.0 `CompositeCalibrator` falls back to default
  weights (composite signal) when the schema_version is 1.

### Test count

828 tests passing, 1 skipped (Phoenix health-check in test mode).

## [0.4.0] - 2026-06-22

### Added

- Golden set + quality metrics module (Commit 1): field F1,
  schema conformance, ANLS, ECE, Brier, AUROC, coverage at
  target accuracy, reliability diagram, eval report.
- Per-field isotonic confidence calibration (Commit 2):
  PAVA-based calibrator, JSON artifact, `just
  eval-fit-calibrator` target.
- Self-refine reflection loop (Commit 3): re-invokes the LLM
  with validation feedback on failure, up to
  `max_reflection_attempts` times.
- LangGraph checkpointing + interrupt (Commit 4):
  `await_review` node, `SqliteSaver` for production,
  `InMemorySaver` for tests, `Command(resume=...)` from the
  review endpoint.
- OpenTelemetry + Phoenix (Commit 5): full pipeline tracing
  with the OpenInference LangChain instrumentor, Phoenix
  service in `docker-compose.yml`.
- G-Eval LLM-as-judge (Commit 6): scores a sampled fraction
  of completed extractions on four criteria; persists to the
  new `extraction_judgments` table.
- Versioned prompt templates + `schema_version` column
  (Commit 7): `prompts/v1/*.md` with YAML front-matter,
  `just eval-diff` for A/B testing.
- PaddleOCR 3.x API (Commit 8): `predict()` with the
  2.x `ocr()` shim behind `PADDLEOCR_USE_V2=1`.
- Docling parser (Commit 9): IBM structured local parser;
  best for PDFs / DOCX with tables and multi-column layouts.
- VLM-as-extractor (Commit 10): PaddleOCR-VL-1.6 + Ollama
  (glm-ocr in chat mode) for one-shot vision extraction.
- Triage node (Commit 11): records the engine selection
  decision in state for observability; `docs/ENGINES.md`
  is the v0.4.0 reference for engines and the deprecation
  policy.

### Migration

- New columns on `extractions` (`prompt_version`,
  `schema_version`); Alembic migration `0003_prompt_schema_version`.
- New table `extraction_judgments`; Alembic migration
  `0002_judgments`.
- New columns on `extractions` (none — extraction_judgments
  is a separate table).
- The pipeline now has 7 steps instead of 4
  (triage + parse + extract + validate + reflect +
  await_review + finalize). External integrations that read
  the step list should account for the new steps.

## [0.3.0] - 2026-06-22

### Release notes

# Release notes — v0.3.0

**Release date:** 2026-06-22
**Type:** Minor (backward-compatible; one bootstrap step required for existing deployments — see the [Migration Guide](docs/MIGRATION_GUIDE.md))

> v0.3.0 is the **modernization release**. We took a hard look at
> every layer of the codebase and brought it up to current
> production standards: security-by-default, structured logging,
> Prometheus metrics, request-id correlation, magic-byte upload
> validation, a real job queue, Alembic migrations, Docker,
> graceful shutdown, and a CI matrix that catches the regressions
> we used to find in production. Public API is unchanged.

---

## What's new in v0.3.0

### Observability

- **Structured JSON logging via structlog.** Production logs are
  one-record-per-line JSON. Set `LOG_JSON=0` for the
  human-readable console renderer in development.
- **Request id propagation.** Inbound `X-Request-ID` is bound to
  the structlog context and echoed on every response. Every log
  line in a request is correlated.
- **`/metrics` endpoint in Prometheus text format.** Counters
  for extractions, reviews, uploads, and provider errors;
  histograms for end-to-end and per-call latency; a gauge for
  in-flight jobs.
- **Append-only audit log** table (`extraction_audit_log`) that
  records one row per lifecycle event. SQL query examples are in
  the runbook.
- **Log redaction.** API keys, bearer tokens, and long free-text
  fields are stripped from log records before they reach a
  handler.

### Security

- **Magic-byte upload validation.** Every uploaded file is
  sniffed against the four supported signatures (PDF, PNG, JPEG,
  TIFF) and rejected on mismatch. The declared extension and the
  verified type must agree.
- **`OLLAMA_BASE_URL` SSRF guard.** The URL must resolve to a
  loopback / local address. An explicit
  `OLLAMA_ALLOW_PRIVATE_HOSTS=true` opt-out exists.
- **Security headers on every response.** `X-Content-Type-Options:
  nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`,
  and a minimal `Permissions-Policy`.
- **In-process rate limiter** at 60 requests/min/IP via SlowAPI.
  Disabled when `TESTING=1`.

### Production readiness

- **Alembic migrations.** A baseline migration
  (`0001_initial_schema.py`) matches the v0.2.x schema.
  Existing deployments run `alembic stamp head` once. The app
  runs `alembic upgrade head` automatically on startup.
- **Multi-stage `Dockerfile`** built from `python:3.12.10-slim`
  with a non-root user, `tini` as PID 1, and a healthcheck
  against `/health/ready`. The image is byte-identical to the dev
  environment thanks to `uv sync --frozen`.
- **Graceful shutdown.** SIGTERM drains the in-process job queue
  with a configurable timeout (`JOB_SHUTDOWN_GRACE_SECONDS`,
  default 30s) before exiting. SIGINT and SIGTERM are wired in
  the lifespan.
- **`/health/ready`** endpoint returns 200 once the LLM and OCR
  registries are populated; 503 otherwise. Use it as the
  readiness probe in Kubernetes / Docker.

### Job queue

- **`JobQueue` Protocol** with two backends:
  - **`InProcessJobQueue`** (default). asyncio task tracker with
    a configurable concurrency cap (`JOB_MAX_CONCURRENT`, default
    8). Survives crashes via the existing
    `_recover_orphaned_jobs` sweep.
  - **`ArqJobQueue`** (opt-in via `REDIS_URL`). Persists jobs to
    a Redis list, dispatches them to N arq worker processes, and
    survives API process restarts without losing pending work.

### CI / CD

- **Coverage report** step in CI (gate deferred to v0.4.0 while
  the new modules gain dedicated unit tests).
- **Pyright** in basic mode (non-blocking) runs on every push.
- **TypeScript type-check** (`tsc --noEmit`) in the frontend CI.
- **CodeQL** weekly scan for Python and TypeScript.
- **Dependabot** weekly updates for pip, npm, and GitHub
  Actions, grouped by runtime / dev.
- **Dependency review** action that fails PRs introducing
  high-severity advisories.

### Testing

- **Hypothesis** property-based tests for the LLM output parser
  and schema coercer. 200 examples per test; idempotence,
  round-trip, and unknown-field-drop invariants.
- **15 new unit tests** for the magic-byte validator, SSRF
  guard, security headers, and rate-limit wiring.
- **5 new unit tests** for the in-process TTL cache.
- **8 new unit tests** for the job-queue backends.
- Total: **392 tests pass**.

### Documentation

- **`docs/DEPLOYMENT.md`** — Docker, systemd, Caddy, nginx,
  observability, backup/restore, migrations, security checklist,
  troubleshooting.
- **`docs/MIGRATION_GUIDE.md`** — v0.2.x → v0.3.0 step by step.
- **`docs/RUNBOOK.md`** — operator reference for the on-call
  rotation.
- **`docs/FAQ.md`** — twenty most-asked questions.
- **`docs/adr/`** — Architecture Decision Records (LangGraph
  pipeline, SQLite default, secure-by-default).

### Developer experience

- **`justfile`** with `just install`, `just lint`, `just test`,
  `just dev`, `just migrate`, `just release-patch`, etc.
- **`.pre-commit-config.yaml`** running ruff, prettier, and
  standard pre-commit hooks.
- **`.devcontainer/devcontainer.json`** for one-click VS Code /
  Codespaces setup with uv and Node 22 pre-installed.
- **`.editorconfig`** and **`CONTRIBUTING.md`** at the repo root.

### Code quality

- **pyright** basic type-check configuration in `pyproject.toml`.
  47 pre-existing issues remain; the gate is non-blocking for
  v0.3.0 and will tighten in v0.4.0.
- All 93 pre-existing ruff issues fixed; the codebase is
  ruff-clean.
- Three duplicated helpers (`_apply_no_store_headers`,
  `_normalize_utc`, `_duration_ms`) consolidated into
  `app/utils/http.py` and `app/utils/datetime.py`.
- A single `app/constants.py` is the source of truth for
  wire-format strings, log field names, security defaults, and
  rate-limit values.

---

## Breaking changes

**None at the public API level.** All changes are additive
behind new endpoints, new env vars, and new opt-in components.

The **only** mandatory operator action is `alembic stamp head`
on existing v0.2.x databases, documented in the
[Migration Guide](docs/MIGRATION_GUIDE.md) §1.

---

## Known issues carried forward

- **Single-worker scaling.** The in-process job queue is the
  default. To scale out, set `REDIS_URL` and run the Arq worker
  process.
- **PaddleOCR / GLM-OCR trade-offs.** PaddleOCR is a traditional
  text-detection model; GLM-OCR is a vision-language model. The
  right choice depends on the document layout.
- **No multi-user auth.** Authentication is the operator's
  responsibility — use a reverse proxy.

---

## Credits

Built by the v0.3.0 modernization effort. 31 commits since v0.2.0
across eight logical phases.


### Added

### Changed

### Fixed

### Added

### Changed

### Fixed


### Added

### Changed

### Fixed

## [0.3.0] - 2026-06-22

> The modernization release. Backward-compatible at the API level;
> one bootstrap step required for existing deployments
> (`alembic stamp head`). See
> [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md).

### Added

#### Observability
- **structlog** for structured logging, with JSON in production
  and a console renderer in dev. Every record carries a
  `timestamp`, `service`, `level`, and (during a request)
  `request_id`.
- **`RequestContextMiddleware`** reads or generates an
  `X-Request-ID`, binds it to the structlog context, and echoes
  it on the response.
- **`/metrics`** Prometheus endpoint with counters, gauges, and
  histograms for extractions, reviews, uploads, in-flight jobs,
  end-to-end and per-call latency, and provider errors.
- **`extraction_audit_log`** append-only table; one row per
  lifecycle event (started, ocr_complete, extracted, completed,
  needs_review, failed, retried, review_submitted).
- **Log redaction** for `api_key=`, `bearer` tokens, and long
  free-text fields.

#### Security
- **Magic-byte upload validation** against the PDF, PNG, JPEG,
  and TIFF signatures. Uploads whose verified type disagrees
  with the declared extension are rejected with 400.
- **`OLLAMA_BASE_URL` SSRF guard.** Loopback-only by default;
  `OLLAMA_ALLOW_PRIVATE_HOSTS=true` opt-out.
- **Security headers middleware**: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`.
- **Rate limiter** via SlowAPI at 60 req/min/IP. Disabled when
  `TESTING=1`.

#### Production readiness
- **Alembic** with a baseline `0001_initial_schema.py`
  migration. `init_db()` runs `alembic upgrade head` on startup
  and falls back to `Base.metadata.create_all` if Alembic is
  missing or `SKIP_ALEMBIC=1`.
- **Multi-stage `Dockerfile`** built from `python:3.12.10-slim`
  with a non-root user, tini PID 1, and a healthcheck against
  `/health/ready`.
- **`docker-compose.yml`** starts the app and a local Ollama
  with `glm-ocr` pre-pulled, with a named volume for app data.
- **`/health/ready`** endpoint returns 200 when the LLM and OCR
  registries are populated; 503 otherwise.
- **Graceful shutdown.** SIGTERM drains the in-process queue
  with `JOB_SHUTDOWN_GRACE_SECONDS` timeout (default 30s).

#### Job queue
- **`JobQueue` Protocol** with two backends:
  - `InProcessJobQueue` (default): asyncio task tracker with a
    concurrency cap.
  - `ArqJobQueue` (opt-in via `REDIS_URL`): pushes jobs to a
    Redis list; consumed by an arq worker.
- The `create_extraction` and `retry_extraction` routers use
  the queue instead of `fastapi.BackgroundTasks`.

#### Performance
- **In-process TTL cache** for the public `/api/providers/*`
  endpoints (parsers, llm, config). Module-level
  `config_cache`, `parsers_cache`, `llm_providers_cache`.

#### Testing
- **Hypothesis** property-based tests for the LLM output parser
  and schema coercer. 200 examples per test.
- **15 new security tests**, **5 new cache tests**, **8 new
  job-queue tests**, plus the property suite.
- **Total: 392 tests pass.**

#### CI / CD
- **Pyright** (basic mode, non-blocking) in CI.
- **TypeScript type-check** (`tsc --noEmit`) for the frontend.
- **CodeQL** weekly scan for Python and TypeScript.
- **Dependabot** weekly updates for pip, npm, and GitHub
  Actions, grouped by runtime / dev.
- **Dependency review** action that fails PRs introducing
  high-severity advisories.

#### Developer experience
- **`justfile`** with `just install`, `just lint`, `just test`,
  `just dev`, `just migrate`, `just release-{patch,minor,major}`.
- **`.pre-commit-config.yaml`** (ruff, prettier, standard hooks).
- **`.devcontainer/devcontainer.json`** (uv + Node 22 + VS Code
  extensions).
- **`pyright`** configuration in `pyproject.toml`.

#### Documentation
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Docker, systemd,
  Caddy, nginx, observability, backup/restore, migrations,
  security checklist, troubleshooting.
- [`docs/MIGRATION_GUIDE.md`](docs/MIGRATION_GUIDE.md) — v0.2.x →
  v0.3.0.
- [`docs/RELEASE_NOTES.md`](docs/RELEASE_NOTES.md) — full feature
  list and breaking-change note.
- `docs/UPGRADE_SUMMARY.md` — historical one-page table removed in v4.
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — operator reference.
- [`docs/FAQ.md`](docs/FAQ.md) — frequently asked questions.
- [`docs/adr/0001-record-architecture-decisions.md`](docs/adr/0001-record-architecture-decisions.md)
  — ADR index.
- [`docs/adr/0002-langgraph-for-pipeline.md`](docs/adr/0002-langgraph-for-pipeline.md).
- `docs/adr/0003-sqlite-wal-default.md` — historical database ADR removed in v4.
- [`docs/adr/0004-secure-by-default.md`](docs/adr/0004-secure-by-default.md).
- `CONTRIBUTING.md` moved to the repo root (GitHub convention).
- `.editorconfig` for project-wide style defaults.

### Changed

- All 93 pre-existing ruff issues fixed; the codebase is
  ruff-clean.
- The three duplicated helpers (`_apply_no_store_headers`,
  `_normalize_utc`, `_duration_ms`) consolidated into
  `app/utils/http.py` and `app/utils/datetime.py`.
- A single `app/constants.py` is the source of truth for
  wire-format strings, log field names, security defaults, and
  rate-limit values.
- `pyproject.toml` is the single source of dependency truth.
  `requirements.txt` removed.
- The `runtime` extras in `pyproject.toml` now also include
  `structlog`, `prometheus-client`, `slowapi`, `arq`, and `redis`.
- `README.md` updated with a Section 7 (security) and a Section
  8 (production readiness).
- The FastAPI app version bumped to `0.3.0`.

### Fixed

- `_list_provider_statuses_excludes_internal_fallback_by_default`
  test updated to include `glmocr` in the user-selectable list.
- `test_info` version assertion updated to `0.3.0`.

## [0.2.0] - 2026-06-22

### Added

- **GLM-OCR parser engine.** New `glmocr` parser runs the GLM-OCR
  vision-language OCR model against a local Ollama server
  (default `http://localhost:11434`, model `glm-ocr:latest`).
  Enable with `ENABLE_GLM_OCR=true`; supports PNG, JPEG, TIFF.
  Includes a text-cleanup pass that strips GLM-OCR's
  HTML/markdown scaffolding and deduplicates repeated
  transcriptions.
- **uv-managed project.** Top-level `pyproject.toml` and
  `.python-version` (3.12.10) with optional extras for `paddleocr`,
  `ollama`, `test`, and `lint`. Run `uv venv --python 3.12.10 .venv`
  then `uv pip install -e ".[test,lint,ollama]"`. `uv.lock` is
  committed for reproducible installs.
- **Zero-to-hero docs.** New `docs/ARCHITECTURE.md`,
  `docs/DEVELOPMENT.md`, `docs/GLM_OCR.md`, and
  `docs/LIMITATIONS.md`.
- **13 new unit tests** for the GLM-OCR provider in
  `backend/tests/test_glm_ocr_provider.py`.

### Changed

- README rewritten as a professional, zero-to-hero guide.
- `backend/app/models/enums.py` — `ParserEngine` now includes
  `GLMOCR = "glmocr"`.
- `backend/app/services/ocr/registry.py` — `AUTO_PRIORITY` now
  starts with GLM-OCR before PaddleOCR; `_import_builtin_providers`
  registers the new engine.
- `backend/app/models/schemas.py` — `OCREngineFlags` exposes a
  `glm_ocr: bool` field.
- `backend/app/routers/providers.py` — `/api/providers/config`
  returns the new `glm_ocr` flag.
- `backend/.env.example` — documents the new env vars
  (`ENABLE_GLM_OCR`, `OLLAMA_BASE_URL`, `OLLAMA_GLM_OCR_MODEL`,
  `GLM_OCR_TIMEOUT_SECONDS`).
- `frontend/src/lib/api.ts` — `ParserEngine` mirror enum and
  display-name map include `glmocr`.
- `pyproject.toml` (root) — consolidated project metadata, deps,
  pytest, and ruff configuration.

### Fixed

- The OCR registry test
  (`test_list_provider_statuses_excludes_internal_fallback_by_default`)
  was hard-coded to expect only `paddleocr`; updated to include
  `glmocr` in the user-selectable list.

## [2026-06-13]

### Added

- OSS companion documentation initialized (license, contributing,
  security, conduct, changelog).
