# Development

Paperplane is a Python 3.12 FastAPI backend and a Next.js TypeScript frontend.

```powershell
uv sync --locked
cd frontend
npm ci
```

Run both with `./scripts/dev.ps1`, or start them separately as shown in
[RUN_APP.md](RUN_APP.md).

## Important paths

- `backend/app/main.py` — application lifespan and health endpoints
- `backend/app/routers/dpt_api.py` — public `/v2` routes
- `backend/app/services/agentic/parsing.py` — request-level parse orchestration
- `backend/app/services/parsing/v2_pipeline.py` — page processing and verification
- `backend/app/services/agentic/contracts.py` — public output contract
- `frontend/src/app/page.tsx` — upload and result workspace
- `frontend/src/lib/api.ts` — browser API client

## Checks

```powershell
uv run ruff check backend/app backend/tests
uv run pyright backend/app
uv run pytest -q

cd frontend
npm test
npm run build
```

Keep changes narrow. Update user-facing docs whenever behavior or configuration changes.
Never commit secrets or real source documents.
