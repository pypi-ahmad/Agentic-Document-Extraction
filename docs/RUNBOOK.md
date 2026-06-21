# Runbook

> Operator reference for the on-call rotation.

---

## 1. Health checks

| Check | URL | When it fails |
| --- | --- | --- |
| Liveness | `GET /health` | Process is hung or OOM. Restart. |
| Readiness | `GET /health/ready` | Database, LLM registry, or OCR registry unreachable. Inspect logs and provider keys. |
| Metrics | `GET /metrics` | Prometheus scrape failure. Verify the path is reachable. |

A liveness-restart should only trigger when the readiness check
also fails, otherwise a noisy network blip will cost you uptime.

---

## 2. Common log queries

```bash
# Last 100 HTTP access lines.
jq 'select(.event == "http.request")' < /var/log/ade/ade.jsonl | tail -100

# All 5xx responses in the last hour.
jq -r 'select(.event == "http.request" and .status_code >= 500)
       | "\(.timestamp) \(.method) \(.path) \(.status_code) req=\(.request_id)"' \
       < /var/log/ade/ade.jsonl \
  | since 1h

# Audit trail for one extraction.
jq --arg id "abc123" 'select(.extraction_id == $id)' < /var/log/ade/ade.jsonl

# Provider errors.
jq 'select(.event | test("provider.*error"))' < /var/log/ade/ade.jsonl

# Job-queue drain events.
jq 'select(.event | test("job_queue.*"))' < /var/log/ade/ade.jsonl
```

---

## 3. Failure modes and what to do

### 3.1 Extraction is stuck in `processing`

A row that has been `processing` for more than 5 minutes is
abandoned. On the next startup, the `_recover_orphaned_jobs`
sweep in `app/main.py` will mark it `failed` with a clear error
message. To force the recovery without a restart:

```bash
sqlite3 /var/lib/ade/db/extraction.db \
  "UPDATE extractions SET status = 'failed', error = 'Manually marked failed by ops', completed_at = datetime('now') WHERE status IN ('queued', 'processing', 'ocr_complete', 'extracted');"
```

The user can then retry from the UI.

### 3.2 `/health/ready` returns 503 because no LLM provider is ready

Check the env vars:

```bash
docker compose exec app env | grep -E 'OPENAI|GEMINI|ANTHROPIC'
```

The provider keys may be expired, rate-limited, or the SDK may
not be installed in the runtime image. The startup log line
contains the exact cause.

### 3.3 Audit log fills the disk

The `extraction_audit_log` table is append-only. A nightly cron
that archives rows older than 90 days to cold storage is the
recommended pattern. There is no built-in retention because the
policy belongs to the operator, not the application.

### 3.4 Redis is unreachable (Arq backend)

The API stays up but `ArqJobQueue.submit()` raises. The
extraction router converts that into a 503 response, so the user
sees a clear "try again" message. Inspect the Redis connection
in the app's `startup.complete` log line; if the URL is wrong,
restart the app with the right env.

### 3.5 Ollama stops responding

`GLM-OCR` falls back to `PaddleOCR` if the engine is enabled
there, otherwise the image upload fails with a clear error. To
restart Ollama:

```bash
docker compose restart ollama
curl -s localhost:11434/api/tags | head
```

If Ollama is on a separate host, check the `OLLAMA_BASE_URL`
value in the app's env.

---

## 4. Backup and restore

See [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) §6.

---

## 5. Upgrades

```bash
# Pull latest.
git pull

# Rebuild and restart the container.
docker compose build app
docker compose up -d app

# If the upgrade added a migration:
docker compose exec app alembic upgrade head
```

Watch the startup log for `alembic.upgrade_failed`; if you see
it, the app fell back to `Base.metadata.create_all` which may
have left the schema out of sync. Run `alembic upgrade head`
manually and compare the output to the migration list.

---

## 6. Capacity planning

A single uvicorn worker handles roughly:

- 60 requests/min for the health/info/config endpoints
- 10–20 concurrent extractions (default `JOB_MAX_CONCURRENT=8`)

The bottleneck is almost always the LLM call; the application
itself is mostly waiting. To raise throughput, run multiple
workers behind a reverse proxy **and** move the database to
PostgreSQL. SQLite serialises writes and a multi-process uvicorn
will contend on the file.

---

## 7. Security incident

If you suspect a breach:

1. Snapshot the SQLite file and the `artifacts/` directory
   immediately. They are the only persistent state.
2. Rotate all LLM provider keys.
3. Inspect the audit log for unusual `extraction.started` events
   with an unknown `request_id`.
4. Check the uploads directory for unexpected file types
   (the magic-byte validation should have rejected anything that
   was not PDF / PNG / JPEG / TIFF).
5. File an issue with the full timeline.
