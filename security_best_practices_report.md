# Security Best-Practices Review

## Executive summary

Current defaults describe a local-only application but expose both FastAPI and Ollama on every host interface. FastAPI routes have no authentication or authorization, including document listing, artifact download, cancellation, retry, and deletion. On a shared or untrusted network, another host can read documents and artifacts, delete jobs, consume local model capacity, and call Ollama directly.

Review scope: current working tree under `backend/`, `frontend/`, `Dockerfile`, and `docker-compose.yml`. This was a static, read-only review. Existing uncommitted changes were not modified.

## High severity

### SEC-001 — Unauthenticated document APIs are exposed beyond localhost

- Location: `backend/app/config.py:28`; `backend/app/main.py:70-71`; `backend/app/routers/parse_jobs.py:187-461`; `Dockerfile:69`; `docker-compose.yml:7-8`
- Evidence: the server defaults to `0.0.0.0`; Compose publishes `8000:8000`; the parse-job router has no router-level or route-level authentication dependency. It exposes job listing, diagnostics, artifacts, figures, cancellation, resume, retry, events, and deletion.
- Impact: any network peer able to reach port 8000 can enumerate filenames and document metadata, download generated content, observe processing diagnostics, alter job state, delete stored documents, and consume OCR resources.
- Fix: for the stated local-only product, bind host publishing to loopback (`127.0.0.1:8000:8000`) and default non-container serving to `127.0.0.1`. If remote access is required, add centralized router-level authentication plus per-job authorization before exposing the service.
- Mitigation: host firewall allowlist and reverse-proxy authentication until application controls exist.
- False-positive note: severity drops if deployment guarantees host-only reachability outside repository configuration. Verify effective port bindings and firewall rules.

### SEC-002 — Ollama management/inference API is published without a network boundary

- Location: `docker-compose.yml:21-23`
- Evidence: the Ollama container publishes `11434:11434` to all host interfaces. Ollama is intended as an internal dependency of the `app` service and has no application authentication layer here.
- Impact: reachable network peers can invoke the local model service directly, consume CPU/GPU and memory, inspect available models, and access any management operations exposed by the installed Ollama version.
- Fix: remove the Ollama `ports` entry; Compose services can communicate over the internal network using `http://ollama:11434`. If host access is required, bind only `127.0.0.1:11434:11434`.
- Mitigation: host firewall allowlist.
- False-positive note: verify effective Docker publishing and host firewall rules.

## Medium severity

### SEC-003 — Valid uploads can cause disproportionate memory and compute use

- Location: `backend/app/routers/parse_jobs.py:212-219`; `backend/app/services/parsing/ingest.py:39-75,78-112`; `backend/app/config.py:18-25`
- Evidence: upload chunks are retained and then joined into a second contiguous byte buffer; the default limit is 200 MB. Image validation does not cap decoded pixel dimensions. Rendering permits up to 500 pages at up to 300 DPI, with 600-second model timeouts.
- Impact: an unauthenticated client can create memory pressure using concurrent uploads or decompression-heavy images, then occupy the single processing worker for long periods. Network exposure from SEC-001 makes this remotely triggerable on the reachable network.
- Fix: stream uploads directly to a temporary file while hashing and enforcing the byte limit; cap image pixels/dimensions before conversion; define rendered-pixel/page budgets; add request and job admission limits.
- Mitigation: reverse-proxy body limits, connection limits, and rate limits.
- False-positive note: the single job worker limits concurrent model execution but does not limit concurrent upload buffering or queued work.

### SEC-004 — SSE endpoint has no duration or connection bound

- Location: `backend/app/routers/parse_jobs.py:420-442`
- Evidence: each `/events` request loops until a job reaches a terminal state, sleeping and querying repeatedly. No maximum duration, client quota, or application-level connection limit is enforced.
- Impact: clients can open many streams for a non-terminal job, consuming connections and repeated database work until service availability degrades.
- Fix: enforce an SSE lifetime/iteration cap, disconnect checks, and per-client/global connection limits; prefer existing polling if SSE is not required.
- Mitigation: reverse-proxy concurrent-connection and idle-time limits.

## Existing controls observed

- Upload byte and page-count limits exist.
- PDF/image parsers validate basic format and reject encrypted or multi-frame inputs.
- Storage paths are confined below the configured root.
- Database queries use SQLAlchemy expressions rather than string-built SQL.
- Public diagnostics are explicitly shaped before return.
- Generated text previews use React text rendering, not raw HTML.
- Baseline response headers include `nosniff`, frame denial, referrer policy, and permissions policy.
- Python and frontend lockfiles exist; CI uses `uv sync --locked` and `npm ci`.

## Verification gaps

- Dependency vulnerability audits did not run because the available Windows command runner could not launch `npm`; Python advisory scanning was also not completed.
- Runtime firewall, reverse-proxy, and Docker binding behavior were not tested.
- Git-history secret scanning was not performed.

## Recommended order

1. Close both published ports to non-loopback clients.
2. Decide whether remote/multi-user access is supported; if yes, design authentication and per-job authorization before reopening access.
3. Add upload/render budgets and admission controls.
4. Bound SSE sessions.
