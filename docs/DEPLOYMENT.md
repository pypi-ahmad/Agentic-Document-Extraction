# Deployment

> Production deployment guide for Agentic Document Extraction v0.3.0.

The project ships three production paths: **Docker** (recommended for
self-hosting), **systemd** (recommended for bare-metal / VM), and
**direct `uv run`** (for development and CI). All three share the same
runtime contract: a single FastAPI process that talks to a SQLite
file plus optional sidecars (Ollama, Redis, Prometheus).

---

## 1. The contract

- **HTTP API** on `0.0.0.0:8000` by default.
- **Liveness** is `GET /health` (always 200 if the process is up).
- **Readiness** is `GET /health/ready` (200 once the database, the LLM
  registry, and the OCR registry are reachable; 503 otherwise).
- **Metrics** is `GET /metrics` (Prometheus text format).
- **Persistence** is one SQLite file (`extraction.db`) plus two
  directories (`uploads/`, `artifacts/`).
- **Migrations** are managed by Alembic. The Docker image runs
  `alembic upgrade head` implicitly via the lifespan; for manual
  installs, run `alembic upgrade head` once after the first deploy.

The process is **single-worker** by default. Use multiple workers
behind a reverse proxy for throughput; the SQLite file becomes a
contention point at high concurrency, so a future production switch
to PostgreSQL is the next step past v0.3.0.

---

## 2. Docker (recommended)

### 2.1 Single host, everything local

```bash
git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction
cd Agentic-Document-Extraction
export OPENAI_API_KEY=sk-...
docker compose up -d
# API on http://localhost:8000, Ollama on http://localhost:11434
docker compose logs -f app
```

The compose file starts:

- `app` — the FastAPI process, image `agentic-document-extraction:0.3.0`.
- `ollama` — local Ollama with `glm-ocr` pre-pulled (the first start
  takes a few minutes; the data is cached in the `ollama-data`
  volume thereafter).

### 2.2 Bare Ollama on a different host

Set `OLLAMA_BASE_URL=http://ollama.internal:11434` and
`OLLAMA_ALLOW_PRIVATE_HOSTS=true` in the app's environment.

### 2.3 Health

```bash
curl -s localhost:8000/health      # always 200 if the process is up
curl -s localhost:8000/health/ready # 200 once dependencies are reachable
curl -s localhost:8000/metrics     # Prometheus
```

### 2.4 Data volumes

The `app-data` volume holds:

```
/app/data/
├── db/extraction.db
├── uploads/
└── artifacts/
```

Back this volume up the same way you would back up any SQLite file.

### 2.5 Updating

```bash
git pull
docker compose build app
docker compose up -d app
```

Updates are zero-downtime if you front the app with a reverse proxy
that respects the `X-Request-ID` header. The app installs a SIGTERM
handler that drains the in-process job queue before exiting.

---

## 3. systemd (bare-metal / VM)

```ini
# /etc/systemd/system/ade.service
[Unit]
Description=Agentic Document Extraction
After=network.target

[Service]
Type=simple
User=ade
Group=ade
WorkingDirectory=/opt/ade
Environment="PATH=/opt/ade/.venv/bin:/usr/bin"
Environment="DATABASE_URL=sqlite+aiosqlite:////var/lib/ade/extraction.db"
Environment="UPLOAD_DIR=/var/lib/ade/uploads"
Environment="ARTIFACTS_DIR=/var/lib/ade/artifacts"
Environment="OPENAI_API_KEY=sk-..."
ExecStart=/opt/ade/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --app-dir /opt/ade/backend
ExecStop=/bin/kill -TERM $MAINPID
KillSignal=SIGTERM
TimeoutStopSec=45
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd -r -d /opt/ade -s /bin/bash ade
sudo install -d -o ade -g ade /opt/ade /var/lib/ade
sudo -u ade git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction /opt/ade
sudo -u ade bash -c 'cd /opt/ade && uv venv --python 3.12.10 .venv && source .venv/bin/activate && uv pip install -e ".[test,lint]"'
sudo -u ade bash -c 'cd /opt/ade && source .venv/bin/activate && alembic upgrade head'
sudo systemctl daemon-reload
sudo systemctl enable --now ade
sudo journalctl -u ade -f
```

The `TimeoutStopSec=45` aligns with the in-process drain timeout
(`JOB_SHUTDOWN_GRACE_SECONDS` env, default 30s) plus 15s for HTTP
drain. Bump both together if you expect long-running jobs.

---

## 4. Reverse proxy

### 4.1 Caddy (recommended)

```caddy
# /etc/caddy/sites/ade.caddy
ade.example.com {
    reverse_proxy localhost:8000 {
        header_up X-Request-ID {http.request.header.X-Request-ID}
        header_up X-Forwarded-For {http.request.header.X-Forwarded-For}
    }
    encode zstd gzip
    log {
        output file /var/log/caddy/ade.log
    }
}
```

Caddy's automatic HTTPS + the `X-Request-ID` pass-through give the
upstream a stable correlation id from the moment a request hits the
edge.

### 4.2 nginx

```nginx
upstream ade_app {
    server 127.0.0.1:8000;
    keepalive 16;
}

server {
    listen 443 ssl http2;
    server_name ade.example.com;
    ssl_certificate /etc/letsencrypt/live/ade.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/ade.example.com/privkey.pem;

    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "no-referrer" always;
    client_max_body_size 64m;

    location / {
        proxy_pass http://ade_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        proxy_http_version 1.1;
        proxy_read_timeout 300s;
    }
}
```

---

## 5. Observability

### 5.1 Prometheus scrape

```yaml
scrape_configs:
  - job_name: ade
    static_configs:
      - targets: ["ade.example.com"]
    metrics_path: /metrics
    scrape_interval: 30s
```

Key series:

- `ade_extractions_total{status}` — counter, label by terminal status.
- `ade_in_flight_jobs` — gauge.
- `ade_extraction_duration_seconds_*` — histogram, end-to-end.
- `ade_llm_call_duration_seconds_*` and `ade_ocr_call_duration_seconds_*`
  — histograms for per-call latency.
- `ade_reviews_total{decision}` — counter, label by approve / correct / reject.
- `ade_provider_errors_total{provider,category}` — counter.

### 5.2 Logs

Logs are JSON when `LOG_JSON=1` (the default in Docker). Pipe to your
log shipper of choice; each line is one record with at minimum
`event`, `timestamp`, `service`, `level`, and (when in a request
context) `request_id`.

### 5.3 Audit

`SELECT * FROM extraction_audit_log WHERE extraction_id = ?` gives
the full lifecycle of a job, including the request id that triggered
it. The table is append-only by convention; do not expose a write
endpoint.

---

## 6. Backup and restore

The persistent state is one SQLite file plus two directories:

```bash
# Stop the API (or take a SQLite hot backup with the .backup command).
sudo systemctl stop ade

# Snapshot.
sudo tar czf ade-backup-$(date +%F).tgz \
    /var/lib/ade/db/extraction.db \
    /var/lib/ade/uploads \
    /var/lib/ade/artifacts

sudo systemctl start ade
```

For a hot backup, use SQLite's own `.backup` command (no external
dependencies required) and the documented `WAL` checkpoint.

---

## 7. Migrations

```bash
# Check current revision.
alembic current

# Upgrade to the latest.
alembic upgrade head

# Generate a new migration after a model change.
alembic revision --autogenerate -m "add foo"

# Roll back one step.
alembic downgrade -1
```

If you are upgrading from v0.2.x and your `extraction.db` already has
data, run `alembic stamp head` once after the first deploy so
Alembic records the schema as the latest revision without trying to
recreate the tables. The startup code logs a warning if you forget.

---

## 8. Security checklist

- [ ] `OLLAMA_BASE_URL` points at a loopback / local address. If not,
      `OLLAMA_ALLOW_PRIVATE_HOSTS=true` is set explicitly.
- [ ] At least one LLM API key is set. The startup log line
      `startup.complete` only appears if at least one LLM provider
      is ready.
- [ ] Reverse proxy sends `X-Request-ID` (so log correlation survives
      the edge).
- [ ] `LOG_JSON=1` and the log shipper is configured to redact the
      `authorization` and `api_key` patterns (the app redacts them
      but defence in depth is cheap).
- [ ] The `ade-data` volume is encrypted at rest.
- [ ] The reverse proxy terminates TLS and adds the
      `Strict-Transport-Security` header.
- [ ] Backups are taken nightly, off-host, and tested quarterly.

---

## 9. Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `startup.ollama_url_rejected` | OLLAMA_BASE_URL points at a non-loopback host | Set `OLLAMA_ALLOW_PRIVATE_HOSTS=true` |
| `/health/ready` returns 503 | No LLM provider ready | Set at least one of OPENAI/GEMINI/ANTHROPIC API key |
| `extraction.started` audit row but no progress | Job stuck; check the in-process queue | Inspect `/health` for in-flight gauge; restart |
| `extraction.failed` with `error_category=auth` | Bad or missing API key | Re-set the key and retry |
| `extraction.failed` with `error_category=parse_error` | LLM returned invalid JSON | The output parser retries up to `_MAX_LLM_RETRIES`; if it keeps failing, the model is the issue |
| `uploads_total{outcome=magic_mismatch}` increasing | Client is uploading the wrong file type for the extension | Inspect the actual bytes; fix the client |
| Alembic complains the schema is out of date | A previous deploy did not run `alembic upgrade head` | Run `alembic upgrade head` once |
