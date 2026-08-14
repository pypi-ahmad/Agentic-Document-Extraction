# Operations runbook

## Health

```powershell
curl.exe --fail-with-body http://127.0.0.1:8000/health
curl.exe --fail-with-body http://127.0.0.1:8000/health/ready
curl.exe --fail-with-body http://127.0.0.1:8000/info
```

`/health/ready` returns 503 when `OPENAI_API_KEY` is absent. Inspect structured backend
logs for upstream status, request duration, and validation failures.

## Common failures

| Symptom | Action |
|---|---|
| `openai_not_configured` | Set `OPENAI_API_KEY` and restart the backend |
| `openai_request_failed` | Check base URL, network access, quota, and upstream status |
| `too_large` | Reduce the document or adjust the configured upload limit |
| Browser says backend unavailable | Check `PAPERPLANE_BACKEND_ORIGIN` and both processes |
| Request times out | Increase client/proxy timeout or submit a smaller document |

## Restart and recovery

Stop accepting traffic, let active requests finish, then restart the processes. An
interrupted request must be resubmitted by its caller. There is no server-side state to
back up or restore.
