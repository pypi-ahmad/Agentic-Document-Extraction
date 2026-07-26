# Local GLM-OCR Document-to-Markdown Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Replace the extraction product with a local, layout-aware PDF/image parser that produces downloadable LLM-ready Markdown and grounded document artifacts.

**Architecture:** FastAPI runs a pinned GLM-OCR layout pipeline in one bounded worker, preserves reliable PyMuPDF native text, and sends scanned or complex regions to local Ollama. Per-page checkpoints drive recovery and deterministic artifact assembly.

**Tech stack:** Python 3.12, uv, FastAPI, SQLAlchemy/SQLite, PyMuPDF, GLM-OCR, Ollama, Next.js 14, React.

## Tasks

1. Replace dependencies, configuration, ORM models, and Alembic schema; delete legacy extraction data.
2. Implement ingestion, normalized layout contracts, GLM-OCR adapter, routing, Markdown assembly, PDF/crop/bundle generation, and checkpointed worker.
3. Replace job orchestration and REST routes with create/list/detail/SSE/cancel/resume/retry/download/delete contracts.
4. Replace the frontend with new-parse, job, and history routes plus readiness and sanitized Markdown/PDF previews.
5. Remove cloud LLM, schema extraction, review, MCP, legacy tests, prompts, and obsolete documentation.
6. Add unit, API, lifecycle, migration, golden-document, optional Ollama, scale, PDF, and frontend tests.
7. Verify pytest, Ruff, Pyright, Alembic, frontend tests/build, and Docker Compose configuration.

## Acceptance

The application accepts supported documents up to 200 MB/500 pages, survives interruption through page checkpoints, completes with warnings for isolated page failures, produces the specified Markdown and artifacts, never sends content to a cloud service, and exposes no legacy extraction surface.
