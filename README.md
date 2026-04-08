# Agentic Document Extraction

An intelligent document extraction platform that uses OCR and LLMs to extract structured data from documents. Built with FastAPI, LangGraph, React/Next.js, and SQLite.

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
| **PyMuPDF parser** | ✅ Works out of the box | Nothing — bundled with `requirements.txt` | Extracts embedded text from PDFs. Internal helper, not user-selectable; used automatically when the document is a PDF. Does **not** do image-based OCR. |
| **PaddleOCR** | ⚙️ Requires install + flag | `pip install paddleocr paddlepaddle` and `ENABLE_PADDLEOCR=true` in `.env` | Standard PaddleOCR engine for image-based OCR (PNG, JPG, TIFF). This is **not** a vision-language model — it is the traditional PaddleOCR text detection/recognition pipeline. Without this, image uploads have no parser and extraction will fail. |
| **GLM-OCR** | ❌ Not implemented | — | Not implemented. No provider code exists. Listed here for roadmap awareness only. |
| **DeepSeek-OCR** | ❌ Not implemented | — | Not implemented. No provider code exists. Listed here for roadmap awareness only. |
| **OpenAI** | 🔑 Requires API key | `OPENAI_API_KEY` in `.env` | Real implementation. Calls the OpenAI chat completions API. |
| **Google Gemini** | 🔑 Requires API key | `GEMINI_API_KEY` in `.env` | Real implementation. Calls the Gemini API. |
| **Anthropic Claude** | 🔑 Requires API key | `ANTHROPIC_API_KEY` in `.env` | Real implementation. Calls the Anthropic messages API. |
| **Document upload** | ✅ Works out of the box | Nothing | PDF, PNG, JPG/JPEG, TIFF. Stored on local disk. |
| **Schema presets** | ✅ Works out of the box | Nothing | Built-in Invoice and Receipt templates. Create schemas from presets via UI or API. |
| **Schema CRUD** | ✅ Works out of the box | Nothing | Create/edit/delete extraction templates via UI or API. |
| **Validation engine** | ✅ Works out of the box | Nothing | Required-field checks, type validation (number, boolean, date, list, object), pluggable business-rule hooks. |
| **Confidence scoring** | ✅ Works out of the box | Nothing | Per-field confidence scores from LLM, color-coded in UI. Fields below 60% trigger review routing. |
| **Human review** | ✅ Works out of the box | Nothing | Approve, correct (with inline editing), or reject extractions that need review. Full review history. |
| **LLM retry** | ✅ Works out of the box | Nothing | Retryable LLM errors are retried up to 2× with exponential backoff. Attempt count persisted. |
| **SSE live progress** | ✅ Works out of the box | Nothing | Server-Sent Events stream extraction progress in real time. Falls back to polling if SSE disconnects. |
| **Step-level tracking** | ✅ Works out of the box | Nothing | Each pipeline node (Read → Extract → Validate → Finalize) persisted with timing. Visible in UI. |
| **Extraction history** | ✅ Works out of the box | Nothing | Browse past jobs with search, status filter, step progress, and detail panel. Auto-polls in-progress jobs. |
| **Job durability** | ✅ Works out of the box | Nothing | 300s timeout, startup orphan recovery, retry endpoint. `started_at` timestamp for diagnostics. |
| **SQLite database** | ✅ Works out of the box | Nothing | Auto-created on first run. No external DB required. |

### What is NOT implemented

The following OCR engines are on the roadmap but have **no code in this repository**:
- **GLM-OCR** — no provider, no integration, no runtime.
- **DeepSeek-OCR** — no provider, no integration, no runtime.
- **PaddleOCR-VL** (vision-language model) — the current PaddleOCR integration uses the standard text detection/recognition pipeline, not a vision-language model variant.

### What "Auto" mode actually does

- **Parser Auto**: Uses PyMuPDF for PDFs. For images, selects PaddleOCR (standard OCR engine) if installed and enabled; otherwise **fails** (no silent fallback).
- **AI Provider Auto**: Tries providers in priority order (OpenAI → Gemini → Anthropic) and uses the first one with a valid API key. If none are configured, extraction **fails**.
- **AI Model Auto**: Uses the provider's default model (e.g. `gpt-4o` for OpenAI).

### Minimum viable configuration

To actually extract data end-to-end, you need **at minimum**:

1. A PDF document (so PyMuPDF can parse it — no extra install needed), **and**
2. At least one LLM API key (`OPENAI_API_KEY`, `GEMINI_API_KEY`, or `ANTHROPIC_API_KEY`).

Without an LLM key, the parse step succeeds but the extract step fails.

To extract from **images** (PNG/JPG/TIFF), you additionally need PaddleOCR installed and enabled.

## Features

- **Multi-format document upload**: PDF, PNG, JPG/JPEG, TIFF
- **OCR/parsing**: PyMuPDF (bundled, PDF only, internal) + PaddleOCR (optional, standard OCR for images)
- **LLM extraction**: OpenAI, Gemini, Anthropic — all real implementations, all need API keys
- **LLM retry with backoff**: retryable errors retried up to 2× with exponential backoff; attempt count persisted
- **Confidence scoring**: per-field confidence from LLM, color-coded in UI, drives review routing at <60% threshold
- **Dynamic model loading**: model dropdowns populated from provider APIs when credentials are present
- **Schema presets**: built-in Invoice and Receipt templates; create schemas from presets in one click
- **Custom schemas**: define extraction fields (name, type, required) per use case
- **Validation engine**: required-field checks, type validation (number, boolean, date, list, object), pluggable business-rule hooks
- **Human review workflow**: approve, correct (inline editing), or reject extractions. Full review history persisted.
- **SSE live progress**: real-time extraction progress via Server-Sent Events; auto-fallback to polling
- **Step-level tracking**: each pipeline node persisted with timing, visible as progress dots in UI
- **Extraction history**: browse past jobs with status filter, search, step progress, and detail panel. Auto-polls in-progress jobs.
- **Job durability**: 300s timeout, startup orphan recovery, retry endpoint, `started_at` timestamp
- **Provider registry**: auto-routing selects the best available provider; explicit selection supported
- **Cache headers**: static endpoints (presets, config) return `Cache-Control` headers; schema lookups memoized client-side
- **Local-first**: runs entirely on local infrastructure (SQLite, optional local OCR models)

## Known Limitations

- **Job execution uses FastAPI BackgroundTasks** — extraction jobs run in-process. If the server process is killed mid-job, the job row is stuck until the next startup, when orphan recovery marks it as failed. The retry endpoint allows users to re-run. This is intentional for a local-first architecture; production deployments may want an external task queue.
- **Single-worker concurrency** — `BackgroundTasks` runs in the same event loop as the API server. Heavy OCR or LLM calls may block other requests. For high-throughput, consider running multiple worker processes or an external queue.
- **No image OCR without PaddleOCR** — image uploads (PNG, JPG, TIFF) require PaddleOCR to be separately installed and enabled. Without it, Auto mode will reject image files with a clear error.
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
| `DEFAULT_LLM_PROVIDER` | Preferred provider for Auto mode (`openai`, `gemini`, `anthropic`) | No |
| `ENABLE_PADDLEOCR` | Enable PaddleOCR engine (`true`/`false`) | No (default: `false`) |
| `DATABASE_URL` | SQLite connection string | No (default: `sqlite+aiosqlite:///./extraction.db`) |
| `UPLOAD_DIR` | Upload directory path | No (default: `./uploads`) |
| `MAX_UPLOAD_SIZE_MB` | Maximum upload file size in MB | No (default: `50`) |

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
| POST | `/api/schemas/` | Create an extraction schema |
| POST | `/api/extractions/` | Start an extraction job (async) |
| GET | `/api/extractions/{id}` | Get extraction status and result |
| GET | `/api/extractions/{id}/validation` | Get validation details |
| GET | `/api/providers/llm` | List available LLM providers |
| GET | `/api/providers/parsers` | List available OCR/parser engines |
| GET | `/api/providers/llm/{id}/models` | List models for a provider |
