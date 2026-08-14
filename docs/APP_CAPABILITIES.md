# Paperplane capabilities

Paperplane 4.2.1 converts PDFs, images, and modern Office documents into layout-aware
Markdown, hierarchical grounding JSON, and an annotated evidence PDF in one local
Streamlit session.

## Inputs and routing

| Input | Processing path |
|---|---|
| Text-native PDF page | Local Docling conversion |
| Scanned PDF page | Selected cloud vision model |
| Mixed PDF | Automatic per-page Docling/vision routing |
| PNG, JPEG, WebP, TIFF, BMP | Selected cloud vision model |
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
- Six selectable cloud models using their verified production API IDs
- One selected model for drafting and bounded verification, followed by deterministic grounding

## User workspace

- Document preview before parsing
- Output, Annotated PDF, Markdown, and JSON result tabs
- Page, block, engine, duration, format, and warning summaries
- Provider-reported token totals and an expandable estimated-cost calculation
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

The AI selector exposes the six entries in the [model catalog](MODELS.md) and defaults to
GPT-5.6 Luna.

| Mode | Parser model | Vision behavior |
|---|---|---|
| Fast | `paperplane-ade-fast-latest` | Draft and deterministic grounding; no verification pass |
| Balanced | `paperplane-ade-latest` | Verification only for flagged content |
| Audit | `paperplane-ade-audit-latest` | Highest rendering, verification, and repair budget |

Users select one cloud model for vision inference; Docling remains the local native-document
engine. The selected model fills all model-call roles while the mode continues to bound
verification and repair work.
Pricing uses the configured standard rates in [MODELS.md](MODELS.md); provider invoices
remain authoritative.
Paperplane is inspired by ADE's observable workflow, but does not call LandingAI ADE or
claim its benchmark results.
