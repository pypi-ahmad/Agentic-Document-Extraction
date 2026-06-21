# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
