# Run Paperplane

## Fastest option on Windows

Set `OPENAI_API_KEY`, then double-click `Paperplane.cmd`. The launcher starts the backend
and frontend, checks both, opens the browser, and keeps one terminal open for logs. Press
Ctrl+C to stop.

```powershell
./scripts/dev.ps1 -OpenBrowser
```

Optional port selection:

```powershell
./scripts/dev.ps1 -BackendPort 8010 -FrontendPort 3000 -OpenBrowser
```

## Manual startup

Terminal 1:

```powershell
uv sync --locked
uv run uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd frontend
npm ci
$env:PAPERPLANE_BACKEND_ORIGIN = "http://127.0.0.1:8000"
npm run dev
```

Open `http://127.0.0.1:3000`. API docs are at `http://127.0.0.1:8000/docs`.

## Check and parse

```powershell
curl.exe --fail-with-body http://127.0.0.1:8000/health
curl.exe --fail-with-body http://127.0.0.1:8000/health/ready
curl.exe --fail-with-body -X POST http://127.0.0.1:8000/v2/parse `
  -F "file=@sample.pdf" `
  -F "model=paperplane-ade-latest" `
  -o result.json
```

If `API_KEY` is configured, add `-H "X-API-Key: $env:API_KEY"`.

Parsing is synchronous. Keep the request open until the response arrives. There is no job
ID to poll and no server-side run history to recover after a restart.
