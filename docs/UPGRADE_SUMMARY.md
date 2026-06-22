# Upgrade summary — v0.3.0 → v0.4.0

## Highlights

- **Quality + eval layer** (Commits 1-3, 6-7): golden set,
  field F1 / ECE / AUROC, per-field isotonic calibration,
  self-refine reflection loop, G-Eval judge, versioned
  prompts with `just eval-diff` for A/B testing.
- **LangGraph checkpointing + interrupt** (Commit 4):
  `await_review` node, `SqliteSaver` for production,
  `Command(resume=...)` from the review endpoint.
- **OpenTelemetry + Phoenix** (Commit 5): full pipeline
  tracing; Phoenix service in `docker-compose.yml`.
- **PaddleOCR 3.x API** (Commit 8): the 2.x `ocr()` shim
  behind `PADDLEOCR_USE_V2=1`.
- **Docling parser** (Commit 9): IBM structured local
  parser; best for PDFs / DOCX with tables and multi-column
  layouts.
- **VLM-as-extractor** (Commit 10): PaddleOCR-VL-1.6 + Ollama
  (glm-ocr in chat mode) for one-shot vision extraction.
- **Triage node** (Commit 11): engine selection recorded in
  state for observability; `docs/ENGINES.md` is the
  canonical reference.

## File-level changes

- New `prompts/v1/extraction.md` and `prompts/v1/reflection.md`
  (versioned prompt templates).
- New `backend/app/services/eval/{metrics,calibration,judge}.py`.
- New `backend/app/services/extraction/{vlm_extractor,triage}.py`.
- New `backend/app/services/ocr/docling_provider.py`.
- New `backend/app/services/llm/prompts_loader.py`.
- New `backend/app/telemetry.py`.
- New `docs/QUALITY.md`, `docs/ENGINES.md`,
  `docs/observability.md`.
- New `scripts/eval_diff.py`, `scripts/fit_calibrator.py`,
  `scripts/run_eval.py`.
- New Alembic migrations: `0002_judgments`,
  `0003_prompt_schema_version`.

## Stats

- 12 new commits, ~3,800 lines added, ~80 lines removed.
- 96 new tests (538 total passing at release).
- 4 new database tables / column sets.
- 3 new pipeline steps (reflect, await_review, triage).

A one-page summary of the modernization. For step-by-step
instructions see the [Migration Guide](MIGRATION_GUIDE.md); for
the full feature list see the [Release Notes](RELEASE_NOTES.md).

## At a glance

| Layer | Before | After |
| --- | --- | --- |
| **Logging** | stdlib `logging.getLogger` | `structlog` JSON + request-id binding + secret redaction |
| **Metrics** | none | Prometheus text endpoint, 8 series |
| **Audit** | none | `extraction_audit_log` table, 8 event types |
| **Upload validation** | extension + content type | magic-byte sniff against 4 signatures |
| **Ollama URL** | trusted | SSRF guard (loopback-only by default) |
| **Headers** | none | `nosniff`, `DENY`, `Referrer-Policy`, `Permissions-Policy` |
| **Rate limit** | none | 60 req/min/IP in-process via SlowAPI |
| **DB migration** | `Base.metadata.create_all` | Alembic with `alembic upgrade head` on startup |
| **Docker** | none | multi-stage `python:3.12.10-slim`, non-root, tini PID 1 |
| **Shutdown** | none | SIGTERM drain, configurable grace, structured log |
| **Job queue** | `fastapi.BackgroundTasks` | `JobQueue` Protocol + in-process (default) + Arq/Redis (opt-in) |
| **Cache** | none | TTL cache for `/api/providers/*` (3 endpoints) |
| **CI** | ruff + pytest | + pyright, CodeQL, Dependabot, dependency-review, Node 22 |
| **Tests** | 359 | 392 (hypothesis, cache, jobs, security) |
| **Docs** | 4 files | 11 files incl. ADRs, runbook, FAQ, deployment |

## What to do

```bash
# Pull and install.
git pull
uv venv --python 3.12.10 .venv
source .venv/bin/activate
uv pip install -e ".[test,lint,ollama]"

# For an existing v0.2.x database:
alembic stamp head
# (fresh deployments do not need this)

# Run.
just test
just dev
```

## What you keep

- Every public API endpoint, schema, and UI surface.
- The existing SQLite file (it is byte-identical at the schema
  level).
- All existing tests pass.
- The existing `fastapi.BackgroundTasks`-style semantics, in the
  default in-process queue.

## What you trade

- One extra CLI command on first deploy after upgrading
  (`alembic stamp head`).
- Slightly stricter upload validation (rejects bad magic).
- One extra env var to set if you point Ollama at a remote host
  (`OLLAMA_ALLOW_PRIVATE_HOSTS=true`).
- A small but nonzero per-request overhead from the request-id
  middleware and the security headers middleware. Both are
  measured in microseconds.
