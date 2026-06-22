# Agentic Document Extraction

> **Turn messy documents into structured JSON.** Upload a PDF or image,
> describe the fields you want, and let a four-stage LangGraph pipeline
> (parse → extract → validate → finalize) do the rest — with per-field
> confidence scoring and human review when the LLM isn't sure.

Built with **FastAPI**, **LangGraph**, **SQLAlchemy (async)**, **Next.js
14**, and **uv**. Runs locally with zero external infrastructure.

[![Status: Beta](https://img.shields.io/badge/status-beta-blue.svg)](#status)
[![Python: 3.12.10](https://img.shields.io/badge/python-3.12.10-blue.svg)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Table of contents

- [Why this project](#why-this-project)
- [What it does](#what-it-does)
- [Python package](#python-package)
- [Quick start](#quick-start)
- [Supported file types and parsers](#supported-file-types-and-parsers)
- [Configuration](#configuration)
- [API at a glance](#api-at-a-glance)
- [MCP server](#mcp-server)
- [Documentation](#documentation)
- [Testing](#testing)
- [Architecture in one diagram](#architecture-in-one-diagram)
- [Status, limitations, and roadmap](#status-limitations-and-roadmap)

---

## Why this project

Most "document AI" stacks either:

- force you to use a single proprietary OCR/Vision model, or
- hand you a Jupyter notebook that falls apart the moment the invoice
  layout changes by one column.

This project is built around a few beliefs:

1. **The pipeline is the product.** Parsing, extraction, validation,
   and finalization are separate concerns. Each one should be
   swappable, testable, and observable in isolation.
2. **Confidence is a first-class output.** Every field the LLM extracts
   comes with a 0.0–1.0 score. Fields below the threshold are
   *routed* to human review, not silently auto-approved.
3. **The user owns the data.** Documents, schemas, extractions, and
   reviews live in a local SQLite file. No cloud, no account, no
   telemetry.
4. **Pluggable engines beat monolithic models.** Today we support
   three LLM providers and three OCR engines. Adding a fourth should
   not require touching the rest of the code.

---

## What it does

```
Upload  →  Define schema  →  Run extraction  →  Review & export
   PDF      Invoice/Receipt       Parse                Approve
   PNG      Custom fields         Extract              Correct
   JPEG                          Validate             Reject
   TIFF                          Finalize
```

### The four-node pipeline

```
START ──► parse ──► extract ──► validate ──► finalize ──► END
              │           │
              └──fail──►END└──fail──►END
```

| Node      | What it does                                                                                              |
| --------- | ---------------------------------------------------------------------------------------------------------- |
| parse     | Reads text from the document. PyMuPDF for PDFs, **GLM-OCR** or PaddleOCR for images.                       |
| extract   | Sends the text + schema to the LLM. Retries rate limits / 5xx with exponential backoff.                   |
| validate  | Required-field checks, type coercion, per-field confidence, and pluggable business rules.                 |
| finalize  | Stamps the terminal status (`completed` or `needs_review`) and the completion timestamp.                  |

Every node's duration is persisted in `extraction_steps` and surfaced
in the UI.

### Status lifecycle

```
pending → queued → processing → ocr_complete → extracted → completed
                                                         ↘ needs_review
                                                         ↘ failed
```

---

## Python package

You can install the backend as a normal Python package.

```bash
pip install agentic-document-extraction
```

Useful extras:

```bash
# MCP server support
pip install "agentic-document-extraction[mcp]"

# OCR and local-ollama integrations
pip install "agentic-document-extraction[paddleocr,ollama]"

# test and lint tooling
pip install "agentic-document-extraction[test,lint]"
```

After install, the MCP entry point is available as:

```bash
ade-mcp
```

For staging publish checks, TestPyPI install pattern is:

```bash
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple \
  agentic-document-extraction
```

---

## Quick start

### Prerequisites

- **Python 3.12.10** (pinned in `.python-version`; managed by `uv`)
- **Node.js 18+**
- **One** LLM API key (OpenAI, Google Gemini, or Anthropic Claude).
  For image OCR with no API spend, you can also pull **GLM-OCR** into a
  local [Ollama](https://ollama.com) server.

### 1. Clone and enter the project

```bash
git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction.git
cd Agentic-Document-Extraction
```

### 2. Backend

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create the project venv (uses the pinned Python 3.12.10)
uv venv --python 3.12.10 .venv
source .venv/bin/activate

# Install backend + dev extras (test runner, linter, httpx for GLM-OCR)
uv pip install -e ".[test,lint,ollama]"

# Optional: enable local image OCR via Ollama + GLM-OCR
ollama pull glm-ocr:latest
echo "ENABLE_GLM_OCR=true" >> .env

# Configure
cp backend/.env.example backend/.env
# Edit backend/.env — add at least one LLM API key.

# Run
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Interactive API docs: <http://localhost:8000/docs> · <http://localhost:8000/redoc>

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

### 4. First extraction

1. **Upload** a text-based PDF or an image (PNG/JPEG/TIFF).
2. **Templates** → click a preset (Invoice, Receipt, Purchase Order,
   Bank Statement) to materialise a schema.
3. Back on the main page, pick the schema and click **Extract**.
4. Watch real-time progress through the SSE stream.
5. Review the result — approve, correct flagged fields inline, or
   reject.

---

## Supported file types and parsers

| File type  | Auto-routed engine   | Engine notes                                                                |
| ---------- | -------------------- | --------------------------------------------------------------------------- |
| `pdf`      | **PyMuPDF** (built-in) | Text-layer extraction. No external dependency. Fast.                    |
| `png`      | **GLM-OCR** → PaddleOCR | Local vision-language OCR (Ollama) with PaddleOCR fallback.            |
| `jpg/jpeg` | **GLM-OCR** → PaddleOCR | Same as PNG.                                                            |
| `tiff/tif` | **GLM-OCR** → PaddleOCR | Same as PNG.                                                            |

The Auto router always prefers GLM-OCR (if `ENABLE_GLM_OCR=true` and the
local Ollama has the model pulled) and falls through to PaddleOCR if
GLM-OCR is unavailable. PDFs are always read with PyMuPDF — the
Auto router does **not** fall back from PaddleOCR/GLM-OCR to PyMuPDF
for image files, because PyMuPDF only handles PDFs.

Image OCR is **opt-in** by design. Without a working OCR engine the
frontend's parser dropdown will show PaddleOCR/GLM-OCR as greyed out
and uploads of image files will return a clear error.

See [`docs/GLM_OCR.md`](docs/GLM_OCR.md) for the GLM-OCR setup walkthrough.

---

## Configuration

All settings live in `backend/.env` (template in `backend/.env.example`).

### LLM API keys (at least one required for extraction)

| Variable            | Provider          |
| ------------------- | ----------------- |
| `OPENAI_API_KEY`    | OpenAI            |
| `GEMINI_API_KEY`    | Google Gemini     |
| `ANTHROPIC_API_KEY` | Anthropic Claude  |

### Engine / pipeline flags

| Variable                    | Default                  | Description                                                   |
| --------------------------- | ------------------------ | ------------------------------------------------------------- |
| `DEFAULT_LLM_PROVIDER`      | `auto`                   | Preferred provider when in Auto mode.                          |
| `ENABLE_PADDLEOCR`          | `false`                  | Enable PaddleOCR for image OCR (install separately).           |
| `ENABLE_GLM_OCR`            | `false`                  | Enable GLM-OCR (local Ollama) for image OCR.                   |
| `OLLAMA_BASE_URL`           | `http://localhost:11434` | Ollama HTTP endpoint.                                          |
| `OLLAMA_GLM_OCR_MODEL`      | `glm-ocr:latest`         | Ollama model tag for GLM-OCR.                                  |
| `GLM_OCR_TIMEOUT_SECONDS`   | `120`                    | HTTP timeout for one GLM-OCR call.                             |
| `DATABASE_URL`              | `sqlite+aiosqlite:///./extraction.db` | SQLite path.                                       |
| `UPLOAD_DIR`                | `./uploads`              | Where uploaded files are stored.                               |
| `ARTIFACTS_DIR`             | `./artifacts`            | Where pipeline artifacts are stored.                          |
| `MAX_UPLOAD_SIZE_MB`        | `50`                     | Max upload size.                                               |
| `CONFIDENCE_THRESHOLD`      | `0.6`                    | Review routing threshold (0.0–1.0).                            |
| `LLM_MAX_RETRIES`           | `2`                      | Max retries for transient LLM errors.                          |
| `LLM_RETRY_BASE_DELAY`      | `1.0`                    | Backoff base delay in seconds.                                 |
| `CORS_ORIGINS`              | `http://localhost:3000,...` | Comma-separated CORS origins.                                |
| `HOST` / `PORT`             | `0.0.0.0` / `8000`       | Server bind address.                                           |
| `DEBUG`                     | `true`                   | Debug logging.                                                 |

---

## API at a glance

| Method | Path                                      | Description                                    |
| ------ | ----------------------------------------- | ---------------------------------------------- |
| `POST` | `/api/documents/`                         | Upload a document.                             |
| `GET`  | `/api/documents/`                         | List uploaded documents.                       |
| `GET`  | `/api/schemas/presets`                    | List built-in document-type presets.           |
| `POST` | `/api/schemas/presets/{id}`               | Materialise a preset into your own schema.    |
| `POST` | `/api/schemas/`                           | Create a custom schema.                        |
| `POST` | `/api/extractions/`                       | Start an extraction (returns 202 + job id).    |
| `GET`  | `/api/extractions/{id}`                   | Get status and full result.                    |
| `GET`  | `/api/extractions/{id}/stream`            | SSE live progress.                              |
| `POST` | `/api/extractions/{id}/retry`             | Retry a failed extraction.                     |
| `POST` | `/api/extractions/{id}/reviews`           | Submit Approve / Correct / Reject.             |
| `GET`  | `/api/providers/parsers`                  | List available OCR/parser engines.             |
| `GET`  | `/api/providers/llm`                      | List LLM providers + readiness.                |
| `GET`  | `/api/providers/llm/{id}/models`          | Live model catalog for a provider.             |
| `GET`  | `/api/providers/config`                   | Public, no-secret app config (for the UI).     |
| `GET`  | `/health`                                 | Liveness probe.                                |
| `GET`  | `/info`                                   | Runtime capabilities and version metadata.     |

---

## MCP server

v0.6.0 adds a stdio MCP server so MCP-aware clients (Claude Desktop,
Cursor, Cline, Continue) can call extraction tools directly.

### Install MCP extra

```bash
source .venv/bin/activate
uv pip install -e ".[mcp]"
```

### Run MCP server

```bash
# from repo root
just mcp

# or if installed as an entry point
ade-mcp
```

### Example client config (Claude Desktop)

```json
{
  "mcpServers": {
    "agentic-document-extraction": {
      "command": "/ABSOLUTE/PATH/Agentic-Document-Extraction/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/ABSOLUTE/PATH/Agentic-Document-Extraction",
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

Tools exposed by MCP server:

- `extract_document`
- `verify_extraction`
- `resolve_entities`
- `eval_golden_set`

Full guide, tool schemas, and troubleshooting:
[`docs/MCP.md`](docs/MCP.md)

---

## Documentation

The project ships with a zero-to-hero docs set:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — components, data
  flow, persistence model, durability story, and how the LLM/OCR
  registries work.
- [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — environment setup,
  tests, lint, debug, contributing.
- [`docs/GLM_OCR.md`](docs/GLM_OCR.md) — what GLM-OCR is, when to
  use it, how to install it via Ollama, and the contract it exposes
  inside this project.
- [`docs/MCP.md`](docs/MCP.md) — full MCP setup guide, client
  configuration examples, tool I/O contracts, and troubleshooting.
- [`RELEASE.md`](RELEASE.md) — release + package publish workflow,
  including TestPyPI/PyPI trusted publishing.
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) — what this stack
  explicitly does **not** do (scanned-PDF OCR, multi-worker
  queueing, etc.) and why.
- [`CHANGELOG.md`](CHANGELOG.md) — release notes.

---

## Testing

### Backend

```bash
# Activate the venv once
source .venv/bin/activate

# Full suite (no network required — all engines are mocked or stubbed)
pytest backend/tests/ -v

# With coverage
pytest --cov=app --cov-report=term-missing backend/tests/

# MCP server tests only
pytest backend/tests/test_mcp_server.py -v

# Only the GLM-OCR provider
pytest backend/tests/test_glm_ocr_provider.py -v
```

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

### Live validation scripts

These hit a running backend on `:8000` and are **not** part of CI:

```bash
cd backend
python scripts/validate_llm_providers.py
python scripts/e2e_validation.py
```

---

## Architecture in one diagram

```
┌────────────────────┐        ┌────────────────────────────────────────────┐
│  Next.js 14 (FE)   │  HTTP  │  FastAPI Backend                            │
│  React 18          │───────▶│  ┌──────────────────────────────────────┐  │
│  TypeScript        │◀───────│  │  LangGraph Extraction Pipeline       │  │
│  Tailwind CSS      │  SSE   │  │  parse → extract → validate →        │  │
└────────────────────┘        │  │              finalize                │  │
                             │  └──────────────────────────────────────┘  │
                             │  ┌─────────┐ ┌─────────────┐ ┌──────────┐   │
                             │  │ PyMuPDF │ │ LLM         │ │ SQLite   │   │
                             │  │ GLM-OCR │ │ Providers   │ │ (WAL)    │   │
                             │  │ Paddle  │ │ OpenAI /    │ │          │   │
                             │  │   OCR   │ │ Gemini /    │ │          │   │
                             │  │         │ │ Claude      │ │          │   │
                             │  └─────────┘ └─────────────┘ └──────────┘   │
                             └────────────────────────────────────────────┘
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full
breakdown.

---

## Status, limitations, and roadmap

This is **beta software** (0.6.x). It is feature-complete for the
local-first extraction workflow it was designed for, but it is not yet
production-grade at scale. Known limitations:

- **In-process jobs.** Extraction runs through FastAPI
  `BackgroundTasks`. If the process is killed mid-job, recovery on
  the next startup marks those rows `failed` so the user can retry
  manually. Consider an external queue (Celery / Arq / Dramatiq) for
  production.
- **Single worker.** Heavy LLM/OCR calls can block the event loop.
  Run with multiple workers behind a reverse proxy if you need
  throughput.
- **No scanned-PDF OCR.** PDFs are read with PyMuPDF's text layer
  only. If your PDF is image-only, render each page and run it
  through an OCR engine — but this is **not** wired up by default.
- **OCR engines are best-effort.** PaddleOCR is a standard
  text-detection model; GLM-OCR is a vision-language OCR model. Both
  are pull-the-best-shot, not document-AI guarantees.

See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for details and the
[`CHANGELOG.md`](CHANGELOG.md) for what shipped and what's next.

---

## License

[MIT](LICENSE)
