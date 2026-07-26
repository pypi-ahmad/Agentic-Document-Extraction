# Implementation Plan: Interactive Document Inspection and Batch Processing

## Overview

Add a synchronized evidence workspace for source pages, layout regions, OCR/model attempts,
Markdown, and quality diagnostics. Candidate selection remains automatic. Operators can request
targeted page or region reprocessing, and multiple documents can be submitted as a durable batch
with one combined ZIP export.

## Architecture Decisions

- Keep the existing redacted diagnostics API and expose document content only through protected
  job-scoped inspection endpoints.
- Render source pages on demand with the existing PyMuPDF/Pillow stack and draw interactive region
  overlays in React; do not add a browser PDF-rendering dependency.
- Treat ordinary artifacts as draft outputs. A verified bundle is available only when every selected
  page is complete and no disputed region remains.
- Persist batches and reprocessing runs so progress and decisions survive browser/server restarts.
- Reprocessing is user-triggered, but quality comparison and candidate selection are automatic.

## Delivery Order

1. Persistence, response models, and inspection/quality APIs.
2. Agentic page/region reprocessing and revisioned artifacts.
3. Persistent batch creation, progress, and ZIP export.
4. Synchronized document workspace and batch UI.
5. Backend/frontend tests, static checks, build, and manual Docker validation notes.

## Boundaries

- Always preserve existing single-document endpoints and historical audit records.
- Never expose API keys, log document candidate content, or weaken path-scoping checks.
- Do not add free-form text correction or manual candidate-selection controls.
- Keep unrelated dirty-worktree changes untouched.

