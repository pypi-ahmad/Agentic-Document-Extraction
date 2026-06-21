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
