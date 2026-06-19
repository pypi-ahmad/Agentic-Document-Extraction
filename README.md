# Agentic Document Extraction

> **Extract structured data from documents using AI.** Upload a PDF or image, define what fields you need, and let an LLM-powered pipeline parse, extract, validate, and return structured JSON — with human review when confidence is low.

Built with **FastAPI**, **LangGraph**, **Next.js 14**, and **SQLite**. Runs locally with zero external infrastructure.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Testing](#testing)
- [Design Decisions](#design-decisions)
- [Limitations](#limitations)

---

## How It Works

```
Upload Document → Define Schema → Run Extraction → Review & Export
```

1. **Upload** a PDF, PNG, JPG/JPEG, or TIFF/TIF document.
2. **Choose a schema** — pick a built-in preset (Invoice, Receipt, Purchase Order, Bank Statement) or define custom fields.
3. **Run extraction** — the pipeline reads the document, calls an LLM to extract structured data, validates the output, and scores confidence per field.
4. **Review** — fields below the confidence threshold are flagged. Approve, correct inline, or reject.

### Extraction Pipeline

The core pipeline is a four-node [LangGraph](https://github.com/langchain-ai/langgraph) state machine:

```
START → Parse → Extract → Validate → Finalize → END
```

| Node | What it does |
|------|-------------|
| **Parse** | Reads document text using the built-in PyMuPDF PDF reader or PaddleOCR (for images). |
| **Extract** | Sends text + schema to an LLM. Retries transient errors with exponential backoff. Returns per-field confidence scores. |
| **Validate** | Runs required-field checks, type coercion, confidence scoring, and pluggable business rules. |
| **Finalize** | Stamps terminal status (`completed` or `needs_review`) and completion timestamp. |

If any node fails, the pipeline short-circuits with `failed` status. Every node's duration is persisted and visible in the UI.

### Status Lifecycle

```
pending → queued → processing → ocr_complete → extracted → completed
                                                          ↘ needs_review
                                                          ↘ failed
```

---

## Architecture

```
┌──────────────────┐         ┌─────────────────────────────────────────────┐
│   Next.js 14     │  HTTP   │              FastAPI Backend                │
│   React 18       │────────▶│                                             │
│   TypeScript     │◀────────│  LangGraph Pipeline                        │
│   Tailwind CSS   │   SSE   │  Parse → Extract → Validate → Finalize    │
└──────────────────┘         │                                             │
                             │  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
                             │  │ PyMuPDF  │  │ LLM      │  │ SQLite   │  │
                             │  │ Paddle   │  │ Providers │  │ Database │  │
                             │  └──────────┘  └──────────┘  └──────────┘  │
                             └─────────────────────────────────────────────┘
```

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | Next.js 14, React 18, TypeScript, Tailwind CSS | Upload wizard, extraction detail, review UI, history browser |
| Backend | FastAPI, Pydantic v2, SQLAlchemy (async) | REST API, SSE streaming, background job orchestration |
| Pipeline | LangGraph | Stateful extraction graph with retry, validation, and confidence scoring |
| Database | SQLite via aiosqlite | Documents, schemas, extractions, steps, reviews |
| Parsers | PyMuPDF (built-in), PaddleOCR (optional) | PDF text extraction, image OCR |
| LLM Providers | OpenAI, Google Gemini, Anthropic Claude | Structured data extraction from text |

---

## Quick Start

### Prerequisites

- **Python 3.12+**
- **Node.js 18+**
- At least **one LLM API key** (OpenAI, Gemini, or Anthropic)

### 1. Clone

```bash
git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction.git
cd Agentic-Document-Extraction
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Activate
# Windows:    .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — add at least one: OPENAI_API_KEY, GEMINI_API_KEY, or ANTHROPIC_API_KEY

# Start
uvicorn app.main:app --reload --port 8000
```

API docs: [`localhost:8000/docs`](http://localhost:8000/docs) (Swagger) · [`localhost:8000/redoc`](http://localhost:8000/redoc)

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [`localhost:3000`](http://localhost:3000).

### 4. First Extraction

1. **Upload** a text-based PDF.
2. **Templates** → click a preset (e.g., Invoice) to create a schema.
3. Back on the main page, **select the template** and click **Extract**.
4. Watch real-time pipeline progress via SSE.
5. Review results — approve, correct flagged fields inline, or reject.

---

## Usage Guide

### Documents

Supported formats: **PDF**, **PNG**, **JPG/JPEG**, **TIFF/TIF** (up to 50 MB default).

- PDFs are parsed with the **built-in PyMuPDF** text reader — no extra install required.
- Images require **PaddleOCR** installed and enabled (see [PaddleOCR Setup](#paddleocr-setup-optional)).
- Scanned/image-only PDFs are **not** OCR'd by the current parser contract.

### Schemas

Schemas define what fields to extract. Each field has a name, type (`string`, `number`, `boolean`, `date`, `list`, `object`), and required flag.

- **Built-in presets:** Invoice, Receipt, Purchase Order, Bank Statement — one-click creation.
- **Custom schemas:** Define any field set via the UI or API. Duplicate field names are rejected.

### Extraction

Select a document + schema, optionally choose a provider and parser, then click **Extract**.

| Setting | Auto behavior |
|---------|--------------|
| **Parser** | PyMuPDF for PDFs. PaddleOCR for images if available; otherwise fails with a clear error. |
| **AI Provider** | Tries configured `DEFAULT_LLM_PROVIDER` first, then OpenAI → Gemini → Claude. |
| **AI Model** | Provider default (e.g., `gpt-4o-mini`, `gemini-2.0-flash`, `claude-3-5-haiku-20241022`). |

### Human Review

When any field's confidence drops below the threshold (default 60%), the extraction routes to **Needs Review**.

| Decision | Effect |
|----------|--------|
| **Approve** | Accepts the result as-is → status `completed`. |
| **Correct** | Saves inline field edits, clears confidence for corrected fields → status `completed`. |
| **Reject** | Marks extraction failed → retryable via the retry endpoint. |

All decisions are persisted with timestamps and visible in the review history.

### History

Browse past extractions with status filters, search, and step-level progress. In-progress jobs auto-refresh via polling.

---

## Configuration

Copy `backend/.env.example` to `backend/.env`.

### LLM API Keys

At least one is required for extractions to succeed.

| Variable | Provider |
|----------|----------|
| `OPENAI_API_KEY` | OpenAI |
| `GEMINI_API_KEY` | Google Gemini |
| `ANTHROPIC_API_KEY` | Anthropic Claude |

### Options

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_LLM_PROVIDER` | `auto` | Preferred provider for Auto mode |
| `ENABLE_PADDLEOCR` | `false` | Enable PaddleOCR for image OCR |
| `DATABASE_URL` | `sqlite+aiosqlite:///./extraction.db` | Database connection string |
| `UPLOAD_DIR` | `./uploads` | Document storage path |
| `ARTIFACTS_DIR` | `./artifacts` | Pipeline artifacts path |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max upload size |
| `CONFIDENCE_THRESHOLD` | `0.6` | Review routing threshold (0.0–1.0) |
| `LLM_MAX_RETRIES` | `2` | Max retries for transient LLM errors |
| `LLM_RETRY_BASE_DELAY` | `1.0` | Backoff base delay (seconds) |
| `CORS_ORIGINS` | `http://localhost:3000,...` | Allowed CORS origins |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |
| `DEBUG` | `true` | Debug mode |

### PaddleOCR Setup (Optional)

Required only for image files (PNG, JPG/JPEG, TIFF/TIF):

```bash
pip install paddleocr paddlepaddle
```

Set `ENABLE_PADDLEOCR=true` in `.env`.

> PaddleOCR is standard text-detection OCR — not a vision-language model. It does not OCR scanned PDFs.

---

## API Reference

Full interactive docs at [`/docs`](http://localhost:8000/docs) and [`/redoc`](http://localhost:8000/redoc).

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/documents/` | Upload a document |
| `GET` | `/api/documents/` | List documents |
| `GET` | `/api/documents/{id}` | Get document by ID |
| `DELETE` | `/api/documents/{id}` | Delete document |

### Schemas

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/schemas/presets` | List built-in presets |
| `POST` | `/api/schemas/presets/{preset_id}` | Create schema from preset |
| `POST` | `/api/schemas/` | Create custom schema |
| `GET` | `/api/schemas/` | List schemas |
| `GET` | `/api/schemas/{id}` | Get schema |
| `PUT` | `/api/schemas/{id}` | Update schema |
| `DELETE` | `/api/schemas/{id}` | Delete schema |

### Extractions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/extractions/` | Start extraction (async) |
| `GET` | `/api/extractions/` | List extractions |
| `GET` | `/api/extractions/{id}` | Get extraction details |
| `GET` | `/api/extractions/{id}/stream` | SSE live progress |
| `GET` | `/api/extractions/{id}/result` | Result data only |
| `GET` | `/api/extractions/{id}/validation` | Validation state |
| `GET` | `/api/extractions/{id}/steps` | Step-level timing |
| `POST` | `/api/extractions/{id}/retry` | Retry failed extraction |
| `POST` | `/api/extractions/{id}/reviews` | Submit review decision |
| `GET` | `/api/extractions/{id}/reviews` | Review history |

### Providers

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/providers/parsers` | Available parsers |
| `GET` | `/api/providers/llm` | LLM providers |
| `GET` | `/api/providers/llm/{id}/models` | Models for a provider |
| `GET` | `/api/providers/config` | App config (no secrets) |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness (`?detail=true` for stats) |
| `GET` | `/info` | Runtime capabilities |

---

## Testing

### Backend

```bash
cd backend
pytest tests/ -v

# With coverage
pytest --cov=app tests/
```

### Frontend

```bash
cd frontend
npm run lint       # ESLint
npm run build      # Type-check + production build
```

### Validation Scripts

```bash
cd backend

# Provider validation — checks API key config and model listing
python scripts/validate_llm_providers.py

# E2E runtime validation — requires backend running on :8000
python scripts/e2e_validation.py
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **SQLite** | Zero-config, single-file database. No external services. Fits the local-first architecture. |
| **LangGraph** | Typed state machine for the pipeline with built-in streaming, error propagation, and node-level observability. |
| **BackgroundTasks** | In-process execution avoids external queue dependencies. Startup recovery handles orphaned jobs. |
| **SSE + polling fallback** | Detail view uses SSE for live progress; auto-falls back to polling on disconnect. History page uses polling only. |
| **Per-field confidence** | LLM returns confidence per field. Fields below threshold route to human review instead of auto-completing. |
| **Typed enums** | Parser engines, providers, statuses, and review decisions use string enums on both sides for contract safety. |
| **Uncached live endpoints** | Presets and config are cacheable. Extraction, provider status, and health endpoints use `no-store`. |
| **Deprecated endpoint preservation** | Legacy routes kept with `deprecated=True` for backward compatibility. |

---

## Limitations

| Limitation | Detail |
|-----------|--------|
| **In-process jobs** | Extraction runs via `BackgroundTasks`. Killed processes leave orphaned rows recovered on next startup. Consider an external queue for production. |
| **Single-worker** | Heavy LLM/OCR calls can block the event loop. Use multiple workers for throughput. |
| **No image OCR without PaddleOCR** | Image uploads require PaddleOCR installed and enabled. Without it, Auto rejects images with a clear error. |
| **No scanned PDF OCR** | PDFs use the text reader only. Image-only PDFs are not OCR'd. |
| **Standard OCR only** | PaddleOCR uses traditional text detection — not a vision-language model. |
