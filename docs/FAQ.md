# FAQ

> Frequently asked questions about Agentic Document Extraction v0.3.0.

### Why a LangGraph state machine for a four-step pipeline?

It is overkill for the current scope, but it gives us a typed state
model, per-node streaming, and a clean upgrade path to a more
complex pipeline (plan-execute, reflection, multi-pass extraction).
The hand-rolled alternative would reinvent these badly. See
[ADR-0002](adr/0002-langgraph-for-pipeline.md).

### Why SQLite and not Postgres by default?

Local-first, single-host, single-user. SQLite + WAL is enough for
the expected load, and the file is trivial to back up. The same
SQLAlchemy models work against Postgres; the connection string is
the only thing that changes. See
[ADR-0003](adr/0003-sqlite-wal-default.md).

### Why is the rate limiter in-process?

Single-worker, single-process. The in-process limiter is
collision-free for the current scope and avoids a Redis
dependency. When you scale to multiple workers, swap to a
Redis-backed limiter — the `slowapi` config supports it with a
small adapter.

### Why is GLM-OCR opt-in?

Vision-language OCR is a 1.1B-parameter model that needs ~3 GB of
RAM and a GPU to be fast. By default the image parser is just the
PyMuPDF text reader plus a flag for PaddleOCR; turning GLM-OCR on
is an explicit decision because it pulls in a heavyweight
dependency (the Ollama server).

### Why does the upload router do magic-byte validation twice?

The first pass (extension + content type) is the cheap rejection
path. The second pass (sniff_mime on the saved bytes) is the
authoritative one. The cost is one extra `read()` of a 4 KB
buffer; the security value is that a malicious client cannot
slip an `.exe` past by setting the wrong `content_type`.

### Why no auth?

This is a local-first service. Authentication is the operator's
responsibility — put a real auth proxy (Caddy with OIDC, oauth2-proxy,
Tailscale, etc.) in front of the API. The service exposes the
right headers (`X-Content-Type-Options`, `X-Frame-Options`,
`Referrer-Policy`) and a readiness check that respects auth state,
so wiring this up is one Caddyfile away.

### How do I add a new LLM provider?

See [`docs/DEVELOPMENT.md`](DEVELOPMENT.md) §"Adding a new LLM
provider". The summary is: subclass `BaseLLMProvider`, register
in `_import_builtin_providers`, add a `LLMProviderID` enum value,
add a config flag, add a focused test.

### How do I add a new OCR engine?

Same pattern. Subclass `BaseOCRProvider`, register in
`_import_builtin_providers`, add a `ParserEngine` enum value if
the user should pick it directly, append to `AUTO_PRIORITY`,
add a test. The existing
[GLM-OCR provider](../backend/app/services/ocr/glm_ocr_provider.py)
is the canonical example.

### Why is the audit log append-only?

It is the source of truth for "what happened to job X". Updates
would let a bug silently rewrite history. Application code
must go through `record_audit_event`; there is no public mutation
API.

### Why is the job queue in-process by default?

The default deployment is a single host. The in-process queue
keeps the dependency surface small (no Redis). To scale out,
set `REDIS_URL` and an Arq worker process picks up jobs. See
[`docs/DEPLOYMENT.md`](DEPLOYMENT.md) §"Observability" and the
`arq` section in `app/services/jobs.py`.

### How do I migrate an existing v0.2.x database?

Run `alembic stamp head` once after the first deploy. See the
[Migration Guide](MIGRATION_GUIDE.md).

### Where is the request id in the logs?

It is bound to the structlog context for the entire request and
echoed on the response as `X-Request-ID`. A reverse proxy should
forward the inbound `X-Request-ID` so the edge and the app share
the same id.
