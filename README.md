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
- Tamper-evident audit manifests and private replay bundles containing the source,
  rendered pages, sanitized model-call records, outputs, and crop evidence
- Safe partial results when at least one page succeeds after another page exhausts retries

## Processing modes

| Mode | Page pass | Verification | Use when |
|---|---|---|---|
| Economy | 150 DPI Luna draft | Deterministic grounding only | High-volume, clean documents |
| Balanced | 200 DPI Luna draft | At most 2 Terra calls, including 1 crop | Default production workloads |
| Audit | 250 DPI Luna draft | At most 6 Terra calls, including 5 crops | Dense tables, fine print, regulated review |

All OpenAI requests use strict Structured Outputs, `store: false`, explicit prompt-cache
breakpoints, and a 30-minute cache retention request. Persistent page-result caching is
content-addressed by rendered pixels, mode, and prompt version. Unsupported output is
abstained or sent to review; “zero hallucination” is treated as a measurable quality
policy, not an absolute model guarantee.

## Quick start (PowerShell)

Requirements: Python 3.12, `uv`, Node.js 20+, npm, and an OpenAI API key.

```powershell
cd D:\AI\Github\Agentic-Document-Extraction

# Persistent Windows user variables are inherited by newly opened terminals.
if ([string]::IsNullOrWhiteSpace($env:OPENAI_API_KEY)) { throw "OPENAI_API_KEY is not set" }
if ([string]::IsNullOrWhiteSpace($env:OPENAI_BASE_URL)) { throw "OPENAI_BASE_URL is not set" }

.\scripts\dev.ps1
```

The launcher installs locked dependencies when needed, selects available localhost ports,
verifies the V2 API and frontend proxy, and prints both URLs. Press Ctrl+C once to stop
both servers. To request specific ports, pass `-BackendPort 8010 -FrontendPort 3000`.

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
4. Deterministic overlap, duplication, layout, list, and uncovered-ink gates flag pages.
5. Balanced mode asks Terra to reconcile only flagged full pages; remaining disagreements
   receive targeted crop adjudication. Audit reconciles every page.
6. Page tasks are leased from the database, retried, checkpointed, and assembled
   idempotently into document artifacts.

SQLite and local filesystem storage are the development defaults. PostgreSQL leasing
supports multiple workers via `FOR UPDATE SKIP LOCKED`. Generated objects are addressed
through the `ObjectStore` boundary so production deployments can provide managed,
S3-compatible storage without changing extraction contracts.

Each newly completed V2 job exposes `document.md`, `document.json`, `annotated.pdf`,
`audit-manifest.json`, and `evidence-bundle.zip`. The JSON uses `paperplane-document/v3`, stores Markdown per page with
half-open item spans, and embeds grounding, verification provenance, usage/cost, splits,
and optional schema extraction. The original upload is previewed through the authenticated
`GET /api/v2/jobs/{id}/source` endpoint; the annotated PDF supports inline preview and
download from Results.

The default processing recipe is `v9`. Set `V2_RECIPE_VERSION=v8` before starting the
backend for an operator rollback to the legacy verification budget. A job snapshots its
recipe at creation, so changing the environment never changes an in-flight run.

The companion job response adds `assurance`, `timeline`, and `pages` without changing the
synchronous `ParseResponse` or `paperplane-document/v3`. Generic strict extraction accepts
inline JSON Schema at `POST /v2/extract`; the built-in invoice schema is available at
`GET /v2/contracts/presets/invoice-v1`.

## Configuration

`OPENAI_API_KEY` and `OPENAI_BASE_URL` are read automatically from the process
environment. On Windows, persistent user variables are available after opening a new
terminal. Process environment values take precedence over `.env`; copying
`backend/.env.example` to `.env` remains an optional fallback. The base URL may be the
service root or end in `/v1`.

Pricing is not hardcoded because model rates change; supply the six per-million-token
rate variables to enable USD estimates. Keys remain backend-only. Set `API_KEY` and place
the service behind TLS and authentication before exposing it beyond localhost.

Supported inputs are PDF, PNG, JPEG, WebP, and TIFF. Defaults limit documents to 200 MB
and 500 pages; oversized PDF canvases and image frame sets above the decoded-pixel
budget are rejected before rendering. The API binds to `127.0.0.1` by default, and
anonymous local requests still use the configured rate limit. Large documents are
processed as independently leased page tasks, so
completed pages survive worker restarts.

Reusable extraction schemas intentionally reject regular-expression `pattern` rules;
this keeps validation deterministic and avoids attacker-controlled regex backtracking.
Text and JSON artifact previews are capped at 2 MB in the browser, while larger files
remain downloadable. Python and frontend dependency locks are maintained at versions
that pass `pip-audit` and `npm audit`.

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

The suite is offline. To exercise configured models deliberately against a running local
service, run `uv run python scripts/live_canary.py path/to/document.pdf`. The canary is
never invoked by CI and does not print credentials.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md), and
[LICENSE](LICENSE).
