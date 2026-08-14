# Migration from v3 to v4.1

Version 4 is a breaking simplification. Version 4.1 keeps the local boundary and expands
inputs, routing, grounding, and evidence review.

## Removed in v4

- FastAPI and every REST/OpenAPI endpoint
- Next.js, React, TypeScript, Node.js, and npm
- databases, migrations, jobs, workers, queues, polling, cancellation, and resume
- saved artifacts, schemas, evaluations, reviews, and run history
- schema extraction and invoice contracts
- API-key middleware, CORS, rate limiting, and service health endpoints
- Docker and PyPI publishing
- inactive model providers and legacy pipeline modules

External API clients must migrate to the interactive local workspace or build their own
adapter around the framework-neutral `paperplane` package. Paperplane itself no longer
provides a network contract.

## New entrypoint

For Windows users, double-click `Paperplane.cmd`. For development:

```powershell
uv sync --locked
uv run streamlit run streamlit_app.py --server.port=8551
```

Configuration uses `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` for OpenAI, or
`AGNES_API_KEY` for Agnes 2.5 Flash, from user/process environment variables, ignored
`.env`, or ignored Streamlit secrets.

## Added in v4.1

- local Docling parsing for native PDFs and modern Office/OpenDocument/CSV input
- OpenAI vision parsing for scanned PDFs and images
- selectable Agnes 2.5 Flash vision parsing
- automatic per-page routing for mixed PDFs
- shared reading-order Markdown and hierarchical grounding JSON
- HTML tables, atomic-line evidence, and table-cell metadata
- explicit semantic-only Office grounding
- rendered Output, Annotated PDF, Markdown, and JSON tabs
- annotated source overlays and semantic Office evidence reports
- annotated PDF, Markdown, and JSON downloads

The previous server-side artifacts and endpoints have no one-to-one replacement. The
current user contract is one session-local parse result and its three explicit downloads.
