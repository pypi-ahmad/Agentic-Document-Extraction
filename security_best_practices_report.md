# Security Best-Practices Review

_Supersedes the 2026-07-24 review in this file. Both findings from that review are now stale: SEC-001 (parse_jobs.py had no auth) was fixed by the `require_api_key` mechanism added since then — every router now sets `dependencies=[Depends(require_api_key)]` except one, tracked below. SEC-002 (Ollama port published in docker-compose) no longer applies — the current `docker-compose.yml` only defines a `postgres` service, bound to `127.0.0.1`. This review is a fresh pass against current `backend/` (FastAPI) and `frontend/` (Next.js/React) code, scored against `python-fastapi-web-server-security.md` and `javascript-typescript-nextjs-web-server-security.md`._

## Executive summary

The app's authorization model (a single opt-in shared-secret dependency, `require_api_key`, applied per-router) is sound and consistently used — with one router missing it, now fixed during this session. The two live gaps worth prioritizing are: rate-limiting constants that were clearly intended (`RATE_LIMIT_DEFAULT/UPLOAD/EXTRACT`) but never wired to any endpoint, and a Pillow dependency with 20 open CVEs sitting directly in the untrusted-image-processing path. Everything else — SQL injection, command injection, SSRF, secrets handling, XSS, CORS defaults, file-upload validation — checks out clean against the reference specs. The frontend has no server-side routes/actions of its own (pure client shell proxying to the backend), so most Next.js-specific server-security rules don't apply to this codebase.

Review scope: `backend/app/`, `frontend/src/`, `Dockerfile`, `docker-compose.yml`. Static, read-only analysis plus `uvx pip-audit` (backend) and `npm audit` (frontend).

## High severity

### SEC-001 — Rate-limit configuration exists but is never enforced

- Location: `backend/app/constants.py:56-58` (`RATE_LIMIT_DEFAULT`, `RATE_LIMIT_UPLOAD`, `RATE_LIMIT_EXTRACT`)
- Evidence: these three constants are the only references to rate limiting in the entire backend (confirmed via repo-wide grep for `slowapi`, `Limiter`, and the constant names themselves) — no middleware, dependency, or decorator applies them anywhere.
- Impact: one sentence — a caller (with or without `API_KEY`, depending on deployment) can call `/v2/parse` and `/v2/extract` at unbounded frequency, running up the operator's OpenAI bill with no ceiling.
- Fix: wire an actual limiter (e.g., `slowapi`) to the parse/extract routes using the existing constants; if deployed with multiple workers, back it with Redis rather than an in-process store so limits are shared across workers.
- Mitigation: reverse-proxy-level rate limiting until the app-level limiter exists.
- False-positive note: none — this is dead configuration, not a design choice; the constants' existence indicates it was intended.

### SEC-002 — Pillow has 20 known CVEs in the installed version, directly in the untrusted-image path

- Location: `backend/pyproject.toml`/`uv.lock` (Pillow `12.2.0`); consumed by `backend/app/services/parsing/v2_reconciliation.py` (`Image`, `ImageChops`, `ImageDraw`) and `backend/app/services/parsing/v2_pipeline.py` (crop marking) on page renders derived directly from uploaded documents.
- Evidence: `uvx pip-audit` against the exported lockfile: 20 advisories (PYSEC-2026-2253 through PYSEC-2026-3496) against `pillow==12.2.0`, all fixed in `12.3.0`.
- Impact: Pillow processes image bytes derived from attacker-supplied uploads; a native-library vulnerability here is reachable by anyone who can submit a document, not just a theoretical supply-chain concern.
- Fix: bump `pillow` to `12.3.0`. Single-dependency change — read the changelog for the four-version jump's actual behavior diffs before merging, then run the full test suite.
- Mitigation: none in-app today; this is the actual fix, not a workaround.
- False-positive note: verify the 20 advisories are all genuinely fixed by 12.3.0 (pip-audit reports this, but skim the PYSEC entries for any that need a later version).

## Medium severity

### SEC-003 — CORS allows credentials with no code-level guard against a wildcard origin misconfiguration

- Location: `backend/app/main.py:55-61`; `backend/app/config.py:44,72-73`
- Evidence: `CORSMiddleware(allow_origins=settings.cors_origin_list, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`. `cors_origin_list` is a naive comma-split of the `CORS_ORIGINS` env var with no validation rejecting `*`. Current default (`http://localhost:3000,http://127.0.0.1:3000`) is safe, but nothing in code stops an operator from setting `CORS_ORIGINS=*`, which combined with the hardcoded `allow_credentials=True` is exactly the FASTAPI-CORS-001 anti-pattern (Starlette reflects the request `Origin` when `*` is combined with credentials, rather than rejecting it).
- Impact: only realized if an operator misconfigures `CORS_ORIGINS`; if they do, any origin can make credentialed requests against the API.
- Fix: add a startup assertion that raises if `"*"` appears in `cors_origin_list` while `allow_credentials=True`, or drop `allow_credentials=True` entirely since this API uses header-based auth (`X-API-Key`/`Bearer`), not cookies — credentials aren't actually needed for CORS here.
- Mitigation: document the `CORS_ORIGINS` footgun in `docs/DEPLOYMENT.md`.
- False-positive note: not exploitable with current defaults; this is a missing guardrail, not an active vulnerability.

### SEC-004 — OpenAPI docs are enabled by default with no auth in front of them

- Location: `backend/app/main.py:49-54` (`FastAPI(...)` call has no `docs_url`/`redoc_url`/`openapi_url` override)
- Evidence: default FastAPI behavior serves `/docs`, `/redoc`, `/openapi.json` unauthenticated — these paths aren't covered by any router's `Depends(require_api_key)` since they're framework-level, not router-level.
- Impact: if internet-exposed, any visitor can see the full API surface/schema (endpoint list, request/response shapes). Not a data leak by itself, but an information-disclosure amplifier for the next attacker step.
- Fix: set `docs_url=None, redoc_url=None, openapi_url=None` in production, or gate them behind `require_api_key` via a custom route.
- Mitigation: block `/docs`, `/redoc`, `/openapi.json` at the reverse-proxy layer for internet-facing deployments.
- False-positive note: irrelevant for local-only usage (the documented default deployment mode).

### SEC-005 — `npm audit` flags 3 high-severity advisories nested inside `next@16.2.11`

- Location: `frontend/package.json:14` (`"next": "^16.2.11"`); vulnerable `postcss@8.4.31` and `sharp@0.34.5` are bundled *inside* `node_modules/next`, not top-level deps.
- Evidence: `npm audit --omit=dev` reports `postcss <=8.5.17` (XSS in CSS stringify, arbitrary file read via `sourceMappingURL`) and `sharp <0.35.0` (CVE-2026-33327/33328/35590/35591 via bundled libvips), both nested under `next`.
- Impact: depends on whether these nested code paths are reachable at runtime (CSS stringify and image optimization are both things Next.js uses internally) — not confirmed exploitable here, flagging per the audit signal.
- Fix: **do not run `npm audit fix --force`** — its suggested remediation is downgrading `next` to `9.3.3`, an enormous regression, not a fix (the two nested vulnerable packages are pinned by `next` itself; only a newer Next.js release that bundles patched `sharp`/`postcss` actually resolves this). Check for a newer `16.x` patch release and upgrade `next` alone, reading its changelog first.
- Mitigation: none needed beyond the eventual upgrade; not confirmed reachable.
- False-positive note: high — verify whether the app actually exercises Next's CSS-stringify or image-optimization code paths before treating this as urgent; it may be present-but-unreachable.

## Low / informational

### SEC-006 — No `TrustedHostMiddleware`; `Host` header isn't validated at the app layer

- Location: `backend/app/main.py` (no `TrustedHostMiddleware` added)
- Evidence: repo-wide grep confirms no usage.
- Impact: low for this app — no code was found building security-sensitive absolute URLs (password reset links, OAuth callbacks) from the `Host` header, which is the primary risk this control guards against.
- Fix: add `TrustedHostMiddleware` with an explicit allowed-hosts list if/when the app starts generating any Host-derived URLs, or as defense-in-depth now.
- Mitigation: reverse-proxy layer typically handles this via its own `server_name`/`Host` allowlisting.

### SEC-007 — Uvicorn `--proxy-headers` trust boundary depends on unverified deployment topology

- Location: `Dockerfile:86` (`CMD [..., "--proxy-headers", ...]`, no `--forwarded-allow-ips` override)
- Evidence: uvicorn's default `forwarded_allow_ips` is `127.0.0.1` when unset. `docker-compose.yml` in this repo defines only a `postgres` service — no app/reverse-proxy service — so the actual production topology (where the reverse proxy runs relative to the app container) lives entirely in `docs/DEPLOYMENT.md`, outside this repo's enforceable config.
- Impact: if the reverse proxy in a real deployment reaches the app over a network path other than loopback (e.g., a separate Docker container on a bridge network), forwarded headers get silently ignored (fails safe, not open) — a functional gap, not a security hole, unless someone "fixes" it by setting `--forwarded-allow-ips=*`.
- Fix: no code change required; document the expected proxy-to-app network path in `docs/DEPLOYMENT.md` so `forwarded_allow_ips` is set correctly (specific IP/CIDR, never `*`) if the topology needs it.
- False-positive note: current default is the safe one; only flag this if someone widens `forwarded_allow_ips`.

## Existing controls confirmed (unchanged or newly verified this pass)

- Authorization: `require_api_key` dependency now present on every router (`extraction_schemas.py` was the sole gap; fixed this session).
- SQL injection: not applicable — SQLAlchemy ORM (`select().where()`) throughout, no string-built queries found.
- Command injection: not applicable — `asyncio.create_subprocess_exec` with argv lists (no `shell=True`); the only subprocess call (PaddleOCR-VL Docker sidecar) uses a server-generated `job_id`, never attacker input.
- SSRF: no user-controlled URL fetch surface found anywhere in the backend.
- Secrets: none hardcoded in source; `.env*` properly gitignored (`.gitignore:33-35,88`); no `NEXT_PUBLIC_*` variables exposing anything sensitive.
- Auth transport: header-based (`X-API-Key` / `Authorization: Bearer`) with constant-time comparison (`secrets.compare_digest`) — not query-string, no CSRF exposure since no cookie auth is used.
- XSS: React's default escaping is intact; no `dangerouslySetInnerHTML` found in the reviewed components.
- File uploads: mime-type allowlist enforced (`inspect_document`), size/page bounds enforced (`max_upload_size_mb`, `max_document_pages`), storage paths are server-generated UUIDs, and all reads/writes go through `FileStore`'s bounds-checked path resolver.
- Next.js server surface: no `app/**/route.ts` handlers and no `"use server"` actions exist in the frontend — it's a pure client shell that proxies to the backend, so most Next-specific server-security rules (CSRF on Server Actions, cache data leaks, webhook signature verification) don't apply to this codebase as it stands today.

## Recommended order

1. Fix SEC-001 (wire up rate limiting) and SEC-002 (bump Pillow) — both are concrete, scoped, low-risk changes.
2. Decide on SEC-003 (drop `allow_credentials` or add a startup guard) and SEC-004 (gate/disable docs in prod).
3. Track SEC-005 (Next.js nested advisories) against upstream Next.js releases; don't apply the `--force` remediation.
4. Document the SEC-006/SEC-007 deployment assumptions in `docs/DEPLOYMENT.md` — no code change required unless the topology changes.
