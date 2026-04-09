# Agentic Document Extraction

An intelligent document extraction platform that uses a built-in PDF text reader, optional local image OCR, and cloud LLMs to extract structured data from documents. Built with FastAPI, LangGraph, React/Next.js, and SQLite.

## Architecture

```
┌──────────────┐     ┌────────────────────────────────────────────────────┐
│   Next.js    │────▶│                FastAPI Backend                     │
│   Frontend   │◀────│                                                    │
└──────────────┘     │  ┌────────┐  ┌────────┐  ┌──────────┐  ┌───────┐ │
                     │  │ Upload │─▶│  Parse  │─▶│ Extract  │─▶│Validate│ │
                     │  └────────┘  └────────┘  └──────────┘  └───────┘ │
                     │       │           │            │            │      │
                     │       ▼           ▼            ▼            ▼      │
                     │  ┌────────────────────────────────────────────┐    │
                     │  │            SQLite Database                  │    │
                     │  └────────────────────────────────────────────┘    │
                     └────────────────────────────────────────────────────┘
```

## Extraction Pipeline

The core pipeline is built on LangGraph with 4 sequential nodes:

```
START → parse (OCR) → extract (LLM) → validate → finalize → END
```

- **parse** — reads the document using a pluggable OCR/parser engine
- **extract** — sends OCR text + schema to an LLM for structured extraction
- **validate** — runs required-field checks, type checks, and pluggable business rules
- **finalize** — stamps terminal status (`completed` or `needs_review`) and completion time

If parse or extract fails, the pipeline short-circuits to END with `failed` status.

### Status Lifecycle

```
pending → queued → processing → ocr_complete → extracted → completed
                                                         → needs_review
                                                         → failed
```

## Component Readiness

> **Read this first.** Not every option in the UI is equally production-ready. The table below is the ground truth.

| Component | Status | What you need | Notes |
|-----------|--------|---------------|-------|
| **Built-in PDF reader (PyMuPDF)** | ✅ Works out of the box | Nothing — bundled with `requirements.txt` | Extracts embedded text from PDFs. Internal helper, not user-selectable; used automatically for PDFs. Does **not** do image-based OCR. |
| **PaddleOCR (local image OCR)** | ⚙️ Requires install + flag | `pip install paddleocr paddlepaddle` and `ENABLE_PADDLEOCR=true` in `.env` | Local image OCR for PNG, JPG/JPEG, and TIFF/TIF. This is **not** a vision-language model — it is the traditional PaddleOCR text detection/recognition pipeline. Without this, image uploads have no OCR engine and extraction will fail. |
| **OpenAI** | 🔑 Requires API key | `OPENAI_API_KEY` in `.env` | Real implementation. Calls the OpenAI chat completions API. |
| **Google Gemini** | 🔑 Requires API key | `GEMINI_API_KEY` in `.env` | Real implementation. Calls the Gemini API. |
| **Anthropic Claude** | 🔑 Requires API key | `ANTHROPIC_API_KEY` in `.env` | Real implementation. Calls the Anthropic messages API. |
| **Document upload** | ✅ Works out of the box | Nothing | PDF, PNG, JPG/JPEG, TIFF/TIF. Stored on local disk. |
| **Schema presets** | ✅ Works out of the box | Nothing | Built-in Invoice, Receipt, Purchase Order, and Bank Statement templates. Create schemas from presets via UI or API. |
| **Schema CRUD** | ✅ Works out of the box | Nothing | Create/edit/delete extraction templates via UI or API. |
| **Validation engine** | ✅ Works out of the box | Nothing | Required-field checks, type validation (number, boolean, date, list, object), pluggable business-rule hooks. |
| **Confidence scoring** | ✅ Works out of the box | Nothing | Per-field confidence scores from LLM, color-coded in UI. Fields below configurable threshold (default 60%) trigger review routing. |
| **Human review** | ✅ Works out of the box | Nothing | Approve, correct (with inline editing), or reject extractions that need review. Full review history. |
| **LLM retry** | ✅ Works out of the box | Nothing | Retryable LLM errors are retried up to 2× with exponential backoff. Attempt count persisted. |
| **SSE live progress** | ✅ Works out of the box | Nothing | The extraction detail view opens an SSE stream while a job is active. The stream closes at terminal states; if it disconnects mid-run, the UI falls back to polling. |
| **Step-level tracking** | ✅ Works out of the box | Nothing | Each pipeline node (Read → Extract → Validate → Finalize) persisted with timing. Visible in UI. |
| **Extraction history** | ✅ Works out of the box | Nothing | Browse past jobs with search, status filter, step progress, and detail panel. Auto-polls in-progress jobs. |
| **Job durability** | ✅ Works out of the box | Nothing | 300s timeout, startup orphan recovery, retry endpoint. `started_at` timestamp for diagnostics. |
| **SQLite database** | ✅ Works out of the box | Nothing | Auto-created on first run. No external DB required. |

### What is NOT implemented

The following OCR engines are on the roadmap but have **no code in this repository**:
- **GLM-OCR** — no provider, no integration, no runtime.
- **DeepSeek-OCR** — no provider, no integration, no runtime.
- **PaddleOCR-VL** (vision-language model) — the current PaddleOCR integration uses the standard text detection/recognition pipeline, not a vision-language model variant.
- **OCR for image-only/scanned PDFs** — the current local parser contract reads PDFs with the built-in PyMuPDF text extractor; it does not OCR scanned PDF pages.

### What "Auto" mode actually does

- **Parser Auto**: Uses the built-in PDF reader for PDFs. For PNG, JPG/JPEG, and TIFF/TIF files, selects PaddleOCR if installed and enabled; otherwise **fails** (no silent fallback). PaddleOCR is not used for PDFs in the current local contract.
- **AI Provider Auto**: If `DEFAULT_LLM_PROVIDER` is set to a concrete provider and that provider is ready, Auto uses it first. Otherwise Auto falls back through OpenAI → Gemini → Anthropic Claude. If none are ready, extraction **fails**.
- **AI Model Auto**: Uses the provider's default model (e.g. `gpt-4o-mini` for OpenAI, `gemini-2.0-flash` for Gemini, `claude-3-5-haiku-20241022` for Claude).

### Minimum viable configuration

To actually extract data end-to-end, you need **at minimum**:

1. A text-based PDF document (so the built-in PDF reader can parse it — no extra install needed), **and**
2. At least one LLM API key (`OPENAI_API_KEY`, `GEMINI_API_KEY`, or `ANTHROPIC_API_KEY`).

Without an LLM key, the parse step succeeds but the extract step fails.

To extract from **images** (PNG/JPG/JPEG/TIFF/TIF), you additionally need PaddleOCR installed and enabled.

Image-only or scanned PDFs are not OCRed by the current local runtime contract.

## Features

- **Multi-format document upload**: PDF, PNG, JPG/JPEG, TIFF/TIF
- **OCR/parsing**: built-in PDF text reader via PyMuPDF (bundled, internal) + PaddleOCR (optional, local OCR for PNG/JPG/JPEG/TIFF/TIF images)
- **LLM extraction**: OpenAI, Gemini, Anthropic Claude — all real implementations, all need API keys
- **LLM retry with backoff**: retryable errors retried with configurable exponential backoff (default: 2 retries, 1s base delay); attempt count persisted
- **Confidence scoring**: per-field confidence from LLM, color-coded in UI, drives review routing at configurable threshold (default 60%)
- **Dynamic model loading**: model dropdowns populated from provider APIs when credentials are present
- **Schema presets**: built-in Invoice, Receipt, Purchase Order, and Bank Statement templates; create schemas from presets in one click
- **Custom schemas**: define extraction fields (name, type, required) per use case
- **Validation engine**: required-field checks, type validation (number, boolean, date, list, object), pluggable business-rule hooks
- **Human review workflow**: approve, correct (inline editing), or reject extractions. Full review history persisted.
- **SSE live progress**: the extraction detail view subscribes to the SSE stream; if it disconnects, the UI falls back to polling
- **Step-level tracking**: each pipeline node persisted with timing, visible as progress dots in UI
- **Extraction history**: browse past jobs with status filter, search, step progress, and detail panel. In-progress jobs are refreshed by polling; the history page is not an SSE view.
- **Job durability**: 300s timeout, startup orphan recovery, retry endpoint, `started_at` timestamp
- **Provider registry**: auto-routing selects the best available provider; explicit selection supported
- **Cache behavior**: only static presets/config metadata is cacheable; live extraction/status/review endpoints are intentionally uncached
- **Local-first**: runs entirely on local infrastructure (SQLite, optional local OCR models)

## Known Limitations

- **Job execution uses FastAPI BackgroundTasks** — extraction jobs run in-process. If the server process is killed mid-job, the job row is stuck until the next startup, when orphan recovery marks it as failed. The retry endpoint allows users to re-run. This is intentional for a local-first architecture; production deployments may want an external task queue.
- **Single-worker concurrency** — `BackgroundTasks` runs in the same event loop as the API server. Heavy OCR or LLM calls may block other requests. For high-throughput, consider running multiple worker processes or an external queue.
- **No image OCR without PaddleOCR** — image uploads (PNG, JPG/JPEG, TIFF/TIF) require PaddleOCR to be separately installed and enabled. Without it, Auto mode will reject image files with a clear error.
- **No OCR for scanned PDFs** — PDFs are handled by the built-in text reader, not by PaddleOCR. Image-only PDFs therefore are not OCR'd in the current local integration.
- **PaddleOCR is standard OCR, not a vision-language model** — the integration uses the traditional PaddleOCR text detection/recognition pipeline. It does not use PaddleOCR-VL or any vision-language model variant.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt

# Configure environment (optional — only needed for cloud LLM providers)
cp .env.example .env
# Edit .env with your API keys

# Run the server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Open http://localhost:3000
```

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI API key | If using OpenAI |
| `GEMINI_API_KEY` | Google Gemini API key | If using Gemini |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | If using Claude |
| `DEFAULT_LLM_PROVIDER` | Preferred concrete provider for Auto mode (`auto`, `openai`, `gemini`, `anthropic`) | No |
| `ENABLE_PADDLEOCR` | Enable PaddleOCR engine (`true`/`false`) | No (default: `false`) |
| `DATABASE_URL` | SQLite connection string | No (default: `sqlite+aiosqlite:///./extraction.db`) |
| `UPLOAD_DIR` | Upload directory path | No (default: `./uploads`) |
| `ARTIFACTS_DIR` | Extraction artifacts directory path | No (default: `./artifacts`) |
| `MAX_UPLOAD_SIZE_MB` | Maximum upload file size in MB | No (default: `50`) |
| `CONFIDENCE_THRESHOLD` | Fields below this score trigger review routing (0.0–1.0) | No (default: `0.6`) |
| `LLM_MAX_RETRIES` | Max retry attempts for transient LLM errors | No (default: `2`) |
| `LLM_RETRY_BASE_DELAY` | Base delay in seconds for exponential backoff | No (default: `1.0`) |

## Running Tests

```bash
cd backend
pytest tests/ -v

# With coverage
pytest --cov=app tests/
```

Frontend builds are type-checked via:

```bash
cd frontend
npx next build
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/documents/` | Upload a document |
| GET | `/api/documents/` | List all documents |
| GET | `/api/documents/{id}` | Get a document by ID |
| DELETE | `/api/documents/{id}` | Delete a document |
| GET | `/api/schemas/presets` | List built-in schema presets |
| POST | `/api/schemas/presets/{preset_id}` | Create schema from a built-in preset |
| POST | `/api/schemas/from-preset` | Deprecated compatibility alias for preset creation |
| POST | `/api/schemas/` | Create an extraction schema |
| GET | `/api/schemas/` | List all schemas |
| GET | `/api/schemas/{id}` | Get a schema by ID |
| PUT | `/api/schemas/{id}` | Update a schema |
| DELETE | `/api/schemas/{id}` | Delete a schema |
| POST | `/api/extractions/` | Start an extraction job (async) |
| GET | `/api/extractions/` | List extractions (optional `?document_id=`) |
| GET | `/api/extractions/{id}` | Get extraction status and result |
| GET | `/api/extractions/{id}/stream` | SSE live progress stream |
| GET | `/api/extractions/{id}/result` | Get extraction result data only |
| GET | `/api/extractions/{id}/validation` | Get validation details |
| GET | `/api/extractions/{id}/steps` | Get pipeline step records |
| POST | `/api/extractions/{id}/retry` | Retry a failed extraction |
| POST | `/api/extractions/{id}/reviews` | Submit a review decision |
| GET | `/api/extractions/{id}/reviews` | List review history |
| GET | `/api/providers/llm` | List available LLM providers |
| GET | `/api/providers/parsers` | List user-selectable reader/OCR choices (`auto` lives in config; internal PDF helper excluded) |
| GET | `/api/providers/llm/{id}/models` | List models for a provider |
| GET | `/api/providers/config` | App configuration (no secrets) |
| GET | `/health` | Liveness check (`?detail=true` for stats) |
| GET | `/info` | Runtime capabilities and versions, including parser breakdown (user-selectable vs internal) |

Notes:
`/api/providers/parsers` is the user-facing reader/OCR contract.
`/api/providers/ocr` is a deprecated compatibility alias and should not be used for new clients.
`/api/schemas/presets` and `/api/providers/config` are cacheable metadata endpoints.
`/api/providers/parsers`, `/api/providers/llm`, `/api/providers/llm/{id}/models`, `/health`, `/info`, and `/api/extractions/*` are live operational endpoints and are intentionally uncached.
