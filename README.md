# Paperplane

Paperplane is a stateless document-extraction app. Upload a PDF or image and it returns
grounded Markdown plus hierarchical JSON in the same HTTP request. OpenAI
`gpt-5.6-luna` drafts each page, `gpt-5.6-terra` verifies ambiguous content, and PyMuPDF
handles rendering and coordinates.

The app does not save uploads, results, jobs, schemas, or history. The current result lives
in the browser until it is replaced or the page is refreshed.

## Run on Windows

Requirements: Python 3.12, `uv`, Node.js 20+, npm, and `OPENAI_API_KEY`.

Double-click `Paperplane.cmd`, or run:

```powershell
$env:OPENAI_API_KEY = "your-key"
./scripts/dev.ps1 -OpenBrowser
```

The launcher installs locked frontend dependencies, selects free local ports, starts
FastAPI and Next.js, and stops both with Ctrl+C.

Manual startup:

```powershell
uv sync --locked
uv run uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000

cd frontend
npm ci
npm run dev
```

## API

- `POST /v2/parse` — multipart upload with `file` and optional `model`
- `POST /v2/extract` — grounded extraction from Markdown and an inline JSON Schema
- `GET /v2/contracts/presets/invoice-v1` — built-in invoice schema
- `GET /health`, `/health/ready`, and `/info` — service status

Models: `paperplane-ade-fast-latest`, `paperplane-ade-latest`, and
`paperplane-ade-audit-latest`.

```powershell
curl.exe -X POST http://127.0.0.1:8000/v2/parse `
  -F "file=@sample.pdf" `
  -F "model=paperplane-ade-latest" `
  -o result.json
```

Set `API_KEY` to require `X-API-Key` on `/v2/*`. The key and OpenAI credentials remain
server-side.

## Processing flow

```text
upload -> validate -> render pages -> Luna draft -> deterministic grounding
       -> bounded Terra verification -> assemble Markdown and JSON -> response
```

Supported inputs: PDF, PNG, JPEG, WebP, and TIFF. Defaults allow 200 MB and 500 pages.
Long documents are processed synchronously, so deploy with an HTTP timeout appropriate to
your largest input.

## Verify

```powershell
uv run ruff check backend/app backend/tests
uv run pyright backend/app
uv run pytest -q

cd frontend
npm test
npm run build
```

See [architecture](docs/ARCHITECTURE.md), [run guide](docs/RUN_APP.md), and
[limitations](docs/LIMITATIONS.md).
