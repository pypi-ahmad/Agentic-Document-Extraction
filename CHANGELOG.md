# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Trusted Publishing workflows for package releases.** Added
  `.github/workflows/publish-testpypi.yml` and
  `.github/workflows/publish-pypi.yml` to publish built distributions
  through OIDC (no API tokens) to TestPyPI and PyPI.
- **Package-install docs for PyPI/TestPyPI users.** README and
  release docs now include package install commands, extras usage, and
  Trusted Publishing setup notes.

### Changed

- **Prompt assets packaged with wheels/sdists.** Build configuration now
  force-includes `prompts/**` into the wheel under `app/prompts` and
  includes prompts in source distributions.
- **Prompt loader path resolution hardened.** Prompt loading now supports
  repository installs, packaged installs, and an override via
  `ADE_PROMPTS_DIR`.
- **MCP prompt resolution aligned with prompt loader.**
  `app.mcp_server` now loads `v2` extraction prompts through
  `load_prompt(...)`, with fallback template behavior preserved.
- **CI validates build artifacts.** Main CI now runs `uv build` and
  `twine check dist/*` after tests.

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
**Type:** Minor (backward-compatible; one bootstrap step required for existing deployments — see the [Migration Guide](MIGRATION_GUIDE.md))

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
[Migration Guide](MIGRATION_GUIDE.md) §1.

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
- [`docs/UPGRADE_SUMMARY.md`](docs/UPGRADE_SUMMARY.md) — one-page
  at-a-glance table.
- [`docs/RUNBOOK.md`](docs/RUNBOOK.md) — operator reference.
- [`docs/FAQ.md`](docs/FAQ.md) — frequently asked questions.
- [`docs/adr/0001-record-architecture-decisions.md`](docs/adr/0001-record-architecture-decisions.md)
  — ADR index.
- [`docs/adr/0002-langgraph-for-pipeline.md`](docs/adr/0002-langgraph-for-pipeline.md).
- [`docs/adr/0003-sqlite-wal-default.md`](docs/adr/0003-sqlite-wal-default.md).
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
