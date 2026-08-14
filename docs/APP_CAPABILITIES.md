# Paperplane capabilities

Paperplane turns PDFs and document images into grounded Markdown and hierarchical JSON.

## Available

- PDF, PNG, JPEG, WebP, and TIFF upload
- Native PDF text and coordinate alignment
- Headings, paragraphs, lists, tables, figures, forms, and checkboxes
- Page, block, line, and table-cell grounding
- Fast, Balanced, and Audit processing modes
- Bounded Luna drafting and Terra verification
- Partial output when some pages fail
- Inline JSON Schema extraction with field evidence
- Built-in `invoice-v1` extraction contract
- Optional API-key authentication, CORS restrictions, upload limits, and rate limiting
- Next.js visual workspace plus FastAPI/OpenAPI access

## Deliberately absent

Paperplane does not persist uploads, results, run history, reusable schemas, reviews, or
page checkpoints. It does not provide background jobs, polling, cancellation, resume, or
multi-worker coordination. A parse is one request and one response.

## Models and modes

| API model | Behavior |
|---|---|
| `paperplane-ade-fast-latest` | Fast draft with deterministic grounding |
| `paperplane-ade-latest` | Balanced draft with adaptive verification |
| `paperplane-ade-audit-latest` | Highest verification budget |

PyMuPDF performs deterministic rendering and geometry. OpenAI is the active inference
provider; Paperplane does not call LandingAI ADE or claim its benchmark results.

## Output contract

`POST /v2/parse` returns Markdown, a document/page/block hierarchy, coordinates, grounding
methods, page warnings, failed-page information, model usage, and request metadata. The
result can be saved by the caller as JSON or Markdown.
