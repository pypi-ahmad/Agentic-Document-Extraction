# Development


> **V2 status (2026-08-14):** The active runtime is OpenAI-only and uses versioned recipes, bounded Terra verification, safe partial results, and private evidence bundles. This page retains older detail where useful; [README](../README.md) and [V2 architecture](ARCHITECTURE_V2.md) are authoritative for current behavior.

Paperplane has a FastAPI backend, a Next.js frontend, a SQLite development
store, and a document-scoped PaddleOCR-VL GPU Docker worker. Work from the
repository root unless a command says otherwise.

## Setup

```powershell
uv python install 3.12.10
uv sync --locked
Copy-Item backend/.env.example .env
Set-Location frontend
npm ci
```

The official parser runs in its pinned Docker image; do not install
PaddlePaddle in the host virtual environment. Verify Docker GPU access and
pull the image using `docs/RUN_APP.md`. Model files are cached under
`.cache/paddleocr-vl` and are intentionally ignored by Git.

## Run locally

Use separate terminals from the repository root:

```powershell
# Backend
uv run uvicorn app.main:app --app-dir backend --reload --reload-dir backend --host 127.0.0.1 --port 8000

# Frontend
Set-Location frontend
npm run dev
```

If port 8000 is unavailable, run the backend on 8001 and start Next.js with
`$env:PAPERPLANE_BACKEND_ORIGIN = "http://127.0.0.1:8001"`. Restart Next.js
after changing this value. See `docs/RUN_APP.md` for complete PowerShell and
Bash commands.

## Checks

```powershell
uv run pytest backend/tests/unit -q
uv run ruff check backend/app backend/tests scripts
uv run ruff format --check backend/app backend/tests scripts
Set-Location frontend
npm run lint
npm test
npm run build
```

Run the narrowest relevant check during development, then the applicable
backend and frontend checks before opening a pull request.

## Change boundaries

- Treat parse-job records, artifacts, and Alembic revisions as durable public
  behavior; add a migration for incompatible persistence changes.
- Keep document worker input/output JSON compatible with
  `deploy/paddleocr-vl/worker.py`.
- Add a focused unit or API test for behavior changes.
- Never commit `.env`, source documents, generated artifacts, SQLite runtime
  state, or downloaded model weights.
