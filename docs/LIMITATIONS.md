# Limitations

> What this stack explicitly does **not** do, and why.

This project is intentionally scoped: it is a local-first document
extraction service with a clean pipeline, pluggable engines, and a
human-in-the-loop review step. It is not a full enterprise document
AI platform, and these are the known gaps.

---

## 1. In-process job execution

Extraction runs through FastAPI's `BackgroundTasks` inside the
worker process. This is deliberate: it keeps the project dependency-
free (no Redis, no broker, no Celery worker) and lets you `uvicorn
app.main:app` and go.

**Consequence:** if the process is killed (Ctrl-C, OOM, host
restart) while a job is running, the row is left in a non-terminal
state. The startup sweep in `main.py::_recover_orphaned_jobs`
catches this and marks orphaned jobs `failed` with a clear message,
but the user has to retry manually.

**Mitigation if you outgrow this:**

- run a persistent worker (Celery, Arq, Dramatiq, RQ) instead of
  `BackgroundTasks`;
- or front the API with a process manager (systemd, supervisord,
  k8s) that restarts cleanly;
- or convert the pipeline to an external queue (Redis / RabbitMQ)
  and pull the in-process runner out of `app/routers/extractions.py`.

---

## 2. Single-worker, async I/O

LLM calls and OCR calls are async I/O, but the event loop is shared
across the whole process. A 30 s OCR call on a busy event loop can
delay unrelated requests (health, listing, retries) for the same
duration.

**Mitigation:**

- run multiple workers behind a reverse proxy (gunicorn, uvicorn
  workers, or k8s replicas);
- or move the heavy I/O into a separate process so the API stays
  responsive.

---

## 3. PDF text-layer only

PyMuPDF is the only PDF parser. It is fast and dependency-free, but
it only reads the embedded text layer. Image-only / scanned PDFs
have no text layer and are not OCR'd by this project.

**Mitigation if you need it:**

- render each page to an image (PyMuPDF can do this);
- feed each page to GLM-OCR or PaddleOCR;
- build a dedicated `pdf-image-ocr` provider that owns this flow.

The `OCRResult` shape already supports a multi-page provider, so
the change is local to the parser layer.

---

## 4. OCR engines are pull-the-best-shot

Both PaddleOCR (a text-detection model) and GLM-OCR (a
vision-language model) take a single shot at each page. They do
not perform layout analysis, table extraction, or character-level
post-correction. If you need table-aware extraction today, do it
in the prompt to the LLM, not in the OCR engine.

---

## 5. SQLite as the system of record

SQLite is a great single-writer, multi-reader database for a
local-first service. It is not a great database for:

- concurrent writers (e.g. background job + admin UI updates at
  the same instant);
- replication / point-in-time recovery (WAL gives you crash
  recovery, not time travel);
- horizontal scale-out.

If you need any of those, swap the engine in
`backend/app/database.py` for Postgres. The ORM models and Alembic
schema work identically there; only the connection string changes.

---

## 6. No auth, no multi-user

There is no authentication, no authorisation, no per-user tenancy.
The service assumes a single trusted operator on a single host.
Exposing it to the network without putting a real auth proxy in
front is **not safe**.

This is by design for a local-first single-user workflow. If you
need multi-tenant access, you must add auth (an OAuth proxy, JWT,
or session middleware) **before** exposing the port.

---

## 7. No queue back-pressure

The API will accept as many concurrent extraction jobs as you
submit. There is no global rate limit, no per-user quota, and no
back-pressure to upstream providers (we only back off inside a
single LLM call's retry loop). If you script a flood, you may
exceed your LLM provider's rate limit and start seeing
`rate_limit` errors.

---

## 8. Confidence is the LLM's self-report

The `_confidence` map the LLM returns is *its own* self-assessment,
not an independent calibration. A confident-but-wrong extraction
will still get a high score and skip review. Treat the threshold
as a *triage* signal, not a correctness guarantee.

For real calibration, run the extracted values against a labelled
evaluation set and compare them to the model-reported scores
(see `docs/DEVELOPMENT.md` for how to add evaluation scripts).

---

## 9. Not a cloud-OCR replacement

If you need a managed, multi-region, audit-logged, SLA-backed OCR
service, use a cloud provider. This project is the right answer
when you want the pipeline, the schema language, and the human
review flow to be yours, and the OCR/LLM engines to be swappable
plug-ins.
