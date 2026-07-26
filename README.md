# Paperplane

Paperplane converts PDFs and document images into auditable Markdown and structured
JSON. The V2 runtime uses OpenAI only: `gpt-5.6-luna` drafts page structure and
`gpt-5.6-terra` verifies ambiguous high-resolution crops. PyMuPDF performs deterministic
rendering, cropping, native-text alignment, and PDF annotation; it is not an OCR model.

The architecture is independently inspired by public LlamaParse and LandingAI ADE
concepts: ordered grounded chunks, stable block IDs, document splitting, and visual
coordinates. It does not call either vendor service or claim their benchmarks.

## Outputs

- Layout-aware Markdown with stable block anchors
- Hierarchical JSON blocks for text, tables, cells, figures, forms, and checkboxes
- Page and bounding-box citations with exact or crop-refined grounding methods
- Annotated PDF with reading order, status, and source labels
- Mixed-document classification and instance splitting by repeated identifiers
- Optional schema-defined extraction with field-level evidence
- Usage and operator-configured cost reports, including cached input tokens
- Explicit unresolved values and human-review cases instead of unsupported guesses

## Processing modes

| Mode | Page pass | Verification | Use when |
|---|---|---|---|
| Economy | 150 DPI Luna draft | Deterministic grounding only | High-volume, clean documents |
| Balanced | 200 DPI Luna draft | Terra on uncertain crops | Default production workloads |
| Audit | 250 DPI Luna draft | Terra high-resolution inspection | Dense tables, fine print, regulated review |

All OpenAI requests use strict Structured Outputs, `store: false`, explicit prompt-cache
breakpoints, and a 30-minute cache retention request. Persistent page-result caching is
content-addressed by rendered pixels, mode, and prompt version. Unsupported output is
abstained or sent to review; “zero hallucination” is treated as a measurable quality
policy, not an absolute model guarantee.

## Quick start (PowerShell)

Requirements: Python 3.12, `uv`, Node.js 20+, npm, and an OpenAI API key.

```powershell
cd D:\AI\Github\Agentic-Document-Extraction
uv sync --locked --extra test --extra lint
Copy-Item backend\.env.example .env
$env:OPENAI_API_KEY = "your-key"
uv run uvicorn app.main:app --app-dir backend --reload --reload-dir backend --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd D:\AI\Github\Agentic-Document-Extraction\frontend
npm ci
npm run dev
```

Open <http://localhost:3000>. The API is at <http://localhost:8000/docs>.

No Docker, GPU, PaddleOCR, Ollama, or local model weights are required. Docker Compose
is optional and starts PostgreSQL for multi-worker deployments:

```powershell
docker compose up -d postgres
$env:DATABASE_URL = "postgresql+asyncpg://paperplane:paperplane-dev@127.0.0.1:5432/paperplane"
```

## Runtime architecture

1. Validate the upload and render each page deterministically.
2. Luna returns an ordered strict-schema page draft.
3. Native text is snapped to exact PDF word coordinates where possible.
4. Uncertain or complex regions are cropped and independently verified by Terra.
5. Disagreements receive a bounded blind inspection pass; unresolved content abstains.
6. Page tasks are leased from the database, retried, checkpointed, and assembled
   idempotently into document artifacts.

SQLite and local filesystem storage are the development defaults. PostgreSQL leasing
supports multiple workers via `FOR UPDATE SKIP LOCKED`. Generated objects are addressed
through the `ObjectStore` boundary so production deployments can provide managed,
S3-compatible storage without changing extraction contracts.

## Configuration

Copy `backend/.env.example` to `.env`. `OPENAI_API_KEY` is required. Pricing is not
hardcoded because model rates change; supply the six per-million-token rate variables to
enable USD estimates. Keys remain backend-only. Set `API_KEY` and place the service
behind TLS and authentication before exposing it beyond localhost.

Supported inputs are PDF, PNG, JPEG, WebP, and TIFF. Defaults limit documents to 200 MB
and 500 pages. Large documents are processed as independently leased page tasks, so
completed pages survive worker restarts.

## Verification

```powershell
uv run ruff format --check backend\app backend\tests
uv run ruff check backend\app backend\tests
uv run pyright backend\app
uv run pytest backend\tests -q

cd frontend
npx tsc --noEmit
npm run lint
npm test -- --run
npm run build
```

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and
[LICENSE](LICENSE).
