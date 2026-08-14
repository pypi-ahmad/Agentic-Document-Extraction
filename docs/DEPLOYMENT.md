# Deployment

Deploy one FastAPI process and one Next.js process. Paperplane keeps no durable application
state, so it needs no data volume or migration step.

## Required configuration

```text
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.openai.com/v1
```

Recommended for any non-local deployment:

```text
API_KEY=strong-random-secret
CORS_ORIGINS=https://paperplane.example.com
CORS_ALLOW_CREDENTIALS=true
RATE_LIMIT_ENABLED=true
```

Start the API:

```powershell
uv run uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Build and start the frontend with `PAPERPLANE_BACKEND_ORIGIN` pointing to the API origin.
Place both behind TLS. Configure the proxy and client request timeout for the largest
synchronous document you accept.

Use `/health` for liveness and `/health/ready` for OpenAI configuration readiness. A
restart loses no server-managed work history because the service does not create one; any
request in flight must be retried by the caller.
