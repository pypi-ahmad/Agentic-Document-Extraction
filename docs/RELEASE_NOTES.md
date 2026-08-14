# Paperplane v1.0.0


> **V2 status (2026-08-14):** The active runtime is OpenAI-only and uses versioned recipes, bounded Terra verification, safe partial results, and private evidence bundles. This page retains older detail where useful; [README](../README.md) and [V2 architecture](ARCHITECTURE_V2.md) are authoritative for current behavior.

Paperplane now always creates `annotated.pdf`, with type-colored bounding boxes and region labels over the selected source pages. The new Output files gallery lists every public artifact and previews PDFs, images, Markdown, text, and JSON directly in the UI; ZIP bundles remain download-only.

Paperplane v1 replaces the former schema-extraction product with a focused, local, vision-first document parser. Native PDFs, scanned PDFs, and document images now become clean hierarchical Markdown, grounded context, diagnostics, and optional PDF artifacts without hosted model calls.

## Highlights

- LangGraph `StateGraph` pipeline for ingest, visual segmentation, specialist zone processing, layout stitching, reflection, and finalization.
- Complete PaddleOCR-VL 1.6 layout and recognition through pinned local GPU services.
- Optional local or hosted vision-model review and targeted repair.
- Qwen3.5 9B image-to-Markdown review with structured scores and bounded targeted repair.
- Clean Markdown, grounded Markdown, context JSON, diagnostics, searchable PDF, grounding PDF, figure crops, warnings, settings, and ZIP bundle artifacts.
- Durable SQLite jobs, page checkpoints, LangGraph SQLite state, graceful shutdown, resume, cancellation, retry, SSE snapshots, readiness, metrics, and optional OTLP traces.
- A new Next.js workspace for upload, parse settings, source and Markdown preview, progress, diagnostics, and downloads.
- Rewritten README and Zero-to-Hero study handbook.

## Breaking changes

- The document, schema, extraction, review, provider, evaluation, and MCP APIs have been removed.
- The primary API is now `/api/parse-jobs`.
- Hosted OpenAI, Anthropic, and Gemini provider integrations have been removed.
- The database persistence model has been replaced by parse jobs, page checkpoints, and artifacts.
- Python package, FastAPI, frontend, telemetry, and Docker versions are aligned at `1.0.0`.

## Migration warning

Alembic revision `0005_markdown_parser_reset` drops the legacy extraction tables before creating the v1 parser schema. The downgrade cannot reconstruct deleted legacy data.

Back up a pre-v1 database or configure v1 with a new SQLite database file before starting the application.

## Required local models

```bash
ollama pull glm-ocr:latest
ollama pull qwen3.5:9b
```

The default PaddlePaddle dependency is CPU-only. Install a compatible CUDA-enabled PaddlePaddle build before selecting the CUDA layout device.

## Upgrade

```bash
git pull --ff-only
uv sync --locked
cd frontend
npm ci
```

Back up the database, return to the repository root, start Ollama, and then start the FastAPI application. Alembic upgrades run during application startup.

## Verification baseline

- Ruff formatting and linting
- Pyright with zero errors
- Backend unit suite
- Fresh Alembic migration
- Python wheel and source distribution validation
- TypeScript and ESLint
- Next.js production build
- Docker Compose configuration validation

## Known limitations

- This is a local, single-operator application without authentication or tenant isolation.
- One document job runs at a time; region processing within the job is bounded concurrently.
- The first Docker pull is large; subsequent backend restarts reuse the warm parser service.
- The primary parser requires Docker Desktop, WSL2, and an NVIDIA GPU.
- Layout and OCR quality still depends on scan resolution, rotation, handwriting, and document complexity.

## Rollback

Return the application to the previous tag and restore the pre-v1 database backup. Do not run a v0.x application against a database already migrated through revision `0005`.
