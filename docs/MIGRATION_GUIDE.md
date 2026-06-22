# Migration guide: v0.3.x → v0.4.0

> v0.4.0 is the **quality + OCR refresh** release. It adds a
> golden-set-driven eval layer (field F1, ECE, AUROC, Brier,
> reliability diagrams), per-field isotonic confidence
> calibration, a self-refine reflection loop, LangGraph
> checkpointing + interrupt for human review, OpenTelemetry +
> Phoenix tracing, a G-Eval LLM-as-judge, versioned prompts,
> the PaddleOCR 3.x API, a Docling parser, a VLM-as-extractor
> path (PaddleOCR-VL-1.6 + Ollama), and a triage node for
> engine selection.

The HTTP API is unchanged. Internal schema changes:

- New columns on `extractions` (`prompt_version`,
  `schema_version`).
- New table `extraction_judgments`.

## Steps

1. **Pull the new code:**
   ```
   git pull origin main
   git checkout v0.4.0
   ```

2. **Sync dependencies** (new transitive deps: opentelemetry-*
   packages; docling is opt-in via the `docling` extra):
   ```
   uv sync --frozen --all-extras
   ```

3. **Run migrations** (adds `prompt_version`, `schema_version`,
   and the `extraction_judgments` table):
   ```
   alembic upgrade head
   ```

4. **(Optional) Install the new optional engines:**
   ```
   pip install docling                          # Docling parser
   pip install paddleocr-vl>=1.6                # VLM-as-extractor (PaddleOCR-VL)
   pip install "agentic-document-extraction[docling,vlm]"
   ```

5. **(Optional) Enable the new flags** in `.env`:
   ```
   ENABLE_DOCLING=true
   ENABLE_VLM_EXTRACT=false    # opt-in per request
   ```

6. **(Optional) Start the Phoenix service** for trace UI:
   ```
   docker compose up phoenix
   OTEL_EXPORTER_OTLP_ENDPOINT=http://phoenix:4317
   ```

7. **Verify**: the existing test suite (`just test`) and the
   new eval metrics tests (`just test-eval`) should all pass.

## Behavior changes to be aware of

- The pipeline now has **7 steps** instead of 4. External
  integrations that read the step list (UI dashboards, BI
  pipelines) should account for the new steps.
- The `await_review` node is a no-op when the graph is
  compiled without a checkpointer. To enable the interrupt
  + resume flow, pass a checkpointer to
  `build_extraction_graph(...)` (or use
  `build_extraction_graph_with_sqlite(...)`).
- PaddleOCR 3.x is the default path. Set `PADDLEOCR_USE_V2=1`
  to force the legacy 2.x code path on installs that
  cannot upgrade.
- The G-Eval judge samples 5% of completed extractions by
  default. Set `judge_enabled=False` to skip entirely.

## Reverting

The v0.3.0 tag stays on the remote; to roll back:

```
git checkout v0.3.0
alembic downgrade -1   # reverts the 0002 and 0003 migrations
uv sync --frozen       # restore the v0.3.0 lockfile
```

# Migration guide: v0.2.x → v0.3.0

> v0.3.0 is the modernization release. There is **one** required
> migration step (Alembic) and several recommended but optional
> ones. Public API is unchanged; the only breaking change is the
> Alembic bootstrap.

---

## 1. The required step: Alembic

v0.3.0 introduces Alembic. For a fresh deployment nothing changes
— `alembic upgrade head` runs as part of the app startup. For an
existing v0.2.x deployment with an `extraction.db` already on disk,
do this **once**:

```bash
source .venv/bin/activate
# Tell alembic: "the schema in this DB is already the latest revision."
alembic stamp head
```

After that, every subsequent deployment runs `alembic upgrade head`
transparently as part of the app startup.

The baseline migration (`0001_initial_schema.py`) creates six
tables and matches the v0.2.x schema byte-for-byte (plus the new
`extraction_audit_log` table, which is added by a follow-up
migration when the first audit row is written — Alembic handles
this automatically via the `Base.metadata` reflect).

---

## 2. Configuration changes (no action required, but recommended)

| Variable | v0.2.x | v0.3.0 | Note |
| --- | --- | --- | --- |
| `DEFAULT_LLM_PROVIDER` | optional | unchanged | |
| `ENABLE_PADDLEOCR` | optional | unchanged | |
| `ENABLE_GLM_OCR` | — | **new** (`false` by default) | Set to `true` to use the local GLM-OCR engine |
| `OLLAMA_BASE_URL` | — | **new** (`http://localhost:11434`) | Local-only by default; see below |
| `OLLAMA_GLM_OCR_MODEL` | — | **new** (`glm-ocr:latest`) | |
| `GLM_OCR_TIMEOUT_SECONDS` | — | **new** (`120`) | |
| `REDIS_URL` | — | **new** (empty) | Set to `redis://…` to switch the job queue to Arq |
| `JOB_MAX_CONCURRENT` | — | **new** (`8`) | In-process queue concurrency cap |
| `JOB_SHUTDOWN_GRACE_SECONDS` | — | **new** (`30`) | Time to drain in-flight jobs on SIGTERM |
| `LOG_LEVEL` | — | **new** (`INFO`) | |
| `LOG_JSON` | — | **new** (`1`) | Set to `0` for the human-readable console renderer |
| `LOG_SQL` | — | **new** (`0`) | Set to `1` to log every SQL statement |
| `SKIP_ALEMBIC` | — | **new** | Set to `1` to skip alembic on startup (legacy mode) |
| `TESTING` | — | **new** | Set to `1` to disable the in-process rate limiter |

---

## 3. Security policy changes

### 3.1 Upload validation now uses magic bytes

Uploads whose bytes do not match the declared extension are
rejected with `400 Bad Request`. The most common case this
catches is a PDF that was renamed to `.exe`.

If you were relying on the old extension-only check (which is
unsafe by design), the migration is to fix the client. There is
no opt-out: the magic-byte path is the only path.

### 3.2 `OLLAMA_BASE_URL` is now loopback-only by default

If your `OLLAMA_BASE_URL` is `http://ollama.internal:11434`
(remote), set `OLLAMA_ALLOW_PRIVATE_HOSTS=true` in the env. The
app will log a clear `startup.ollama_url_rejected` and refuse to
start until the env is fixed.

### 3.3 New security headers

Every response now carries `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, and `Referrer-Policy: no-referrer`. If
your reverse proxy already sets these, no action is required —
the app's headers are additive.

### 3.4 Rate limiting is now on by default

60 requests per minute per IP. The limiter is in-process and
resets on restart. Set `TESTING=1` to disable (the test suite
does this automatically).

---

## 4. Observability

### 4.1 New endpoints

- `GET /health/ready` — readiness probe; 503 if LLM or OCR
  registries are empty.
- `GET /metrics` — Prometheus text format. Series:
  - `ade_extractions_total{status}`
  - `ade_reviews_total{decision}`
  - `ade_uploads_total{file_type, outcome}`
  - `ade_in_flight_jobs`
  - `ade_extraction_duration_seconds_*`
  - `ade_llm_call_duration_seconds_*`
  - `ade_ocr_call_duration_seconds_*`
  - `ade_provider_errors_total{provider, category}`

### 4.2 Logs

- All log lines are now JSON when `LOG_JSON=1` (the default in
  Docker). Set `LOG_JSON=0` for the human-readable console
  renderer in development.
- Every log line carries a `service` field
  (`agentic-document-extraction`), a `timestamp` in UTC, and
  (during a request) the `request_id` from the inbound
  `X-Request-ID` header.
- API-key-shaped values and `bearer` tokens are redacted from
  log records before they reach a handler.

### 4.3 Audit log

A new `extraction_audit_log` table records one row per
lifecycle event. See [`docs/RUNBOOK.md`](RUNBOOK.md) for query
examples.

---

## 5. Job execution

`fastapi.BackgroundTasks` has been replaced by a
[`JobQueue`](../backend/app/services/jobs.py) abstraction. The
default in-process backend preserves the prior semantics; the
Arq/Redis backend is opt-in via `REDIS_URL`.

To switch to Arq:

```bash
# Start Redis (any standard Redis 5+).
docker run -d --name redis -p 6379:6379 redis:7

# Set the env.
echo "REDIS_URL=redis://localhost:6379/0" >> .env

# Start the API (it will only enqueue).
docker compose up -d app

# Start the Arq worker (separate process).
docker compose exec app arq app.services.jobs.ArqWorkerSettings
```

---

## 6. Container image

The multi-stage `Dockerfile` is new. The image is built from
`python:3.12.10-slim` (matches the `.python-version`), uses
`ghcr.io/astral-sh/uv` in the build stage, and runs as a
non-root user with `tini` as PID 1 for clean SIGTERM forwarding.

If you were using a custom Dockerfile, the new one is a
drop-in replacement:

```bash
docker build -t ade:0.3.0 .
docker run --rm -p 8000:8000 -v $PWD/data:/app/data ade:0.3.0
```

---

## 7. Rollback

v0.3.0 is backward-compatible at the API level. To roll back:

```bash
# Roll back the code.
git checkout v0.2.0
# Restart.
docker compose up -d app
# Migrations: v0.2.x did not use alembic, so the DB schema is
# exactly what v0.2.x expects. No DB action required.
```

If you ran the v0.3.0 app long enough to write audit-log rows
into `extraction.db`, those rows are extra; v0.2.x will simply
ignore them. No data loss.
