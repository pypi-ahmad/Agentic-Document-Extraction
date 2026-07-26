# Local GLM-OCR Markdown Parser Design

## Product

Replace the schema-driven extraction application with a local document parser. Users upload a PDF or single-page image, monitor a durable parse job, preview the resulting Markdown, and download clean Markdown, grounded Markdown, annotated PDFs, figure crops, or a complete bundle.

The application ends at Markdown. It has no cloud LLM providers, extraction schemas, field validation, human review, or MCP server.

## Parsing architecture

FastAPI owns a bounded, single-document worker. Each page is rendered independently and checkpointed. PP-DocLayoutV3 from the pinned `glmocr` SDK supplies ordered semantic regions; PyMuPDF supplies native PDF words; local Ollama `glm-ocr` recognizes scanned or complex text, tables, formulas, and figures.

Hybrid routing preserves healthy native text, uses region-specific GLM-OCR prompts for unreliable or semantic regions, and falls back to full-page recognition when layout analysis fails. Interrupted jobs become paused and resume from completed page checkpoints. Failed pages produce `completed_with_warnings` when other pages succeed.

## Output contract

- `document.md` is clean, LLM-ready Markdown without page metadata.
- `document.grounded.md` contains identical content plus stable page/region anchors and normalized bounding boxes.
- Simple tables use pipe Markdown; complex tables use sanitized HTML.
- Repeating headers, footers, and page numbers are omitted from clean Markdown and retained in grounded Markdown.
- Figures receive concise local descriptions and saved crops.
- The grounding PDF draws region IDs; the searchable PDF adds a best-effort invisible region-level text layer.

## Limits and controls

Inputs are PDF, PNG, JPEG, or single-frame TIFF, at most 200 MB and 500 pages. Curated controls cover page range, hybrid/forced/native-preferred routing, 150/200/300 DPI, layout device, region concurrency 1-8, marginalia policy, figure descriptions, and optional artifacts. Clean and grounded Markdown are mandatory.

## Persistence and API

SQLite stores parse jobs, page checkpoints, and artifact metadata. Large page-layout JSON lives in checksummed files. REST exposes job creation/list/detail, resumable SSE snapshots, cancel/resume/retry, artifact downloads, and deletion. Existing extraction data is intentionally destroyed by the reset migration.

## UI

The frontend has three routes: new parse, job progress/result, and history. Generated Markdown is preview-only. Runtime readiness shows Ollama, model, storage, and device state and gives explicit local setup guidance.

