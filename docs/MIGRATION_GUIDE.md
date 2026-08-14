# Migration from v3 to v4.2.1

Version 4 is a breaking simplification. Version 4.2.1 keeps the local boundary and expands
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

Configuration prefers user/process environment variables. OpenAI uses `OPENAI_API_KEY`
and the optional `OPENAI_BASE_URL`; Agnes 2.5 Flash uses `AGNES_API_KEY`. Ignored `.env`
and Streamlit secrets remain portable fallbacks for other machines. See the complete
[model catalog](MODELS.md).

## Added in v4.1

- local Docling parsing for native PDFs and modern Office/OpenDocument/CSV input
- selectable cloud vision parsing, including OpenAI and Agnes 2.5 Flash
- automatic per-page routing for mixed PDFs
- shared reading-order Markdown and hierarchical grounding JSON
- HTML tables, atomic-line evidence, and table-cell metadata
- explicit semantic-only Office grounding
- rendered Output, Annotated PDF, Markdown, and JSON tabs
- annotated source overlays and semantic Office evidence reports
- annotated PDF, Markdown, and JSON downloads

The previous server-side artifacts and endpoints have no one-to-one replacement. The
current user contract is one session-local parse result and its three explicit downloads.

## Added in v4.2

- a fixed six-model catalog across OpenAI, xAI, Google, Anthropic, and Agnes
- provider-native structured-output adapters
- provider-reported token aggregation and model-cost estimates in the Streamlit UI
- Windows user-environment credential loading with portable local examples
