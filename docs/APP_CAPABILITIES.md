# Paperplane capabilities

Paperplane 4.1.0 converts PDFs, images, and modern Office documents into layout-aware
Markdown, hierarchical grounding JSON, and an annotated evidence PDF in one local
Streamlit session.

## Inputs and routing

| Input | Processing path |
|---|---|
| Text-native PDF page | Local Docling conversion |
| Scanned PDF page | Selected OpenAI or Agnes vision model |
| Mixed PDF | Automatic per-page Docling/vision routing |
| PNG, JPEG, WebP, TIFF, BMP | Selected OpenAI or Agnes vision model |
| DOCX, PPTX, XLSX, ODT, ODP, ODS, CSV | Local Docling; optional selected-model figure descriptions |

Default limits are 200 MB and 500 pages or image frames. Paperplane also bounds PDF page
canvas area and cumulative decoded image pixels. Encrypted and password-protected files are
rejected.

## Extraction and evidence

- Reading-order Markdown with explicit page breaks
- Headings, paragraphs, lists, checkboxes, forms, figures, charts, marginalia, and tables
- HTML tables with row, column, `rowspan`, and `colspan` metadata
- Document, page, block, atomic-line, and table-cell hierarchy
- Exact half-open Unicode Markdown ranges
- One-based physical pages and normalized top-left-origin boxes
- Explicit `semantic_only` grounding when Office geometry is unavailable
- Stable IDs within one response
- Fast, Balanced, and Audit processing policies
- Luna vision drafting with deterministic grounding and bounded Terra verification
- Agnes 2.5 Flash as a single-model alternative for the same pipeline stages

## User workspace

- Document preview before parsing
- Output, Annotated PDF, Markdown, and JSON result tabs
- Page, block, engine, duration, format, and warning summaries
- Source overlays for PDF/image evidence
- Semantic evidence reports for Office content without trustworthy coordinates
- Annotated PDF, Markdown, and JSON downloads
- **New extraction** control that clears the current workspace

## Runtime and setup

- One local Streamlit process bound to `127.0.0.1`
- XSRF protection enabled and Streamlit usage telemetry disabled
- One double-click Windows launcher
- Automatic `uv`, Python 3.12.10, locked dependency, and Docling model setup
- Windows user environment variables with ignored `.env` and Streamlit-secret fallbacks
- Local Docling model-resource caching without document or result caching

## Deliberately absent

Paperplane has no REST API, database, accounts, authentication, background jobs, saved
history, reusable schemas, schema extraction, queues, checkpoints, Docker deployment,
JavaScript frontend, or package publishing.

## Data lifetime

The upload, latest result, and annotated PDF live in Streamlit session memory. Selecting a
different file, starting a new extraction, closing the tab, or stopping the app releases
that state. Downloading an artifact is the user's explicit persistence action. Installed
dependencies and Docling model weights remain on disk; statelessness applies to document
and result data.

## Model mapping

The AI selector defaults to OpenAI. Agnes 2.5 Flash is the alternate vision model.

| Mode | Parser model | Vision behavior |
|---|---|---|
| Fast | `paperplane-ade-fast-latest` | Luna draft and deterministic grounding; no Terra pass |
| Balanced | `paperplane-ade-latest` | Terra checks only for flagged content |
| Audit | `paperplane-ade-audit-latest` | Highest rendering, verification, and repair budget |

Users select OpenAI Luna/Terra or Agnes 2.5 Flash for vision inference; Docling remains the
local native-document engine. Agnes uses `AGNES_API_KEY` and its official Chat Completions
endpoint. With Agnes selected, `agnes-2.5-flash` fills all model-call roles while the mode
continues to bound verification and repair work.
Paperplane is inspired by ADE's observable workflow, but does not call LandingAI ADE or
claim its benchmark results.
