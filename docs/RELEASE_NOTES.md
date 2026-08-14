# Paperplane 4.1.0

Paperplane 4.1.0 produces ADE-inspired, context- and layout-aware Markdown, hierarchical
grounding JSON, and an annotated evidence PDF from one local Streamlit application.

## Added

- Local Docling conversion for native PDFs, Office/OpenDocument files, and CSV
- Six selectable cloud vision models using verified production API IDs
- Provider-native OpenAI/xAI Responses, Google Gemini, Anthropic Messages, and Agnes Chat
  Completions adapters
- Automatic per-page routing for native, scanned, and mixed PDFs
- Shared reading-order Markdown and grounding assembly across all engines
- HTML tables with row, column, `rowspan`, and `colspan` metadata
- Atomic-line evidence and exact Unicode Markdown ranges
- Explicit semantic-only geometry for Office content without physical coordinates
- Optional native-document figure descriptions with explicit unavailable placeholders
- Output, Annotated PDF, Markdown, and JSON result views
- In-memory source overlays and semantic Office evidence reports
- Annotated PDF, Markdown, and JSON downloads
- Fast, Balanced, and Audit processing modes
- Provider-reported token totals and an expandable estimated model-cost calculation
- Streamlit AppTest coverage for the complete result workflow
- One-file Windows setup and launcher with Docling layout/table model download

## Changed

- The selected model's provider key is required only for scans, images, and optional figure
  descriptions
- Native documents can be parsed locally without an external AI provider
- Configuration prefers user/process environment variables, then ignored local fallbacks
- The result and uploaded bytes remain only in the current Streamlit session
- The local Streamlit server uses `http://127.0.0.1:8551` by default
- Releases are source-only GitHub releases

## Still deliberately absent

- FastAPI, REST/OpenAPI endpoints, Next.js, React, Node.js, Docker, and PyPI packaging
- databases, persistence, jobs, queues, run history, and saved artifacts
- schema extraction, reusable schemas, evaluation, and inactive legacy services
- authentication, CORS configuration, rate limiting, telemetry services, and multi-user hosting

See the [migration guide](MIGRATION_GUIDE.md) for the v3-to-v4 transition and
[capabilities](APP_CAPABILITIES.md) for the current contract.
