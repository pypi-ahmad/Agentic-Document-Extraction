# Security best-practices review

Updated 2026-08-14 for the stateless V2 runtime.

## Current controls

- Backend-only OpenAI credentials and optional `X-API-Key` authentication
- Exact-origin CORS validation and security response headers
- Request throttling, upstream timeout, upload byte limits, page limits, and decoded-pixel limits
- Magic-byte/type validation and basename-only upload names
- Strict structured model outputs and bounded verification budgets
- Sanitized client errors and structured logs that avoid document bodies and credentials
- No application persistence of source files or extraction responses

## Deployment requirements

- Terminate TLS at a trusted reverse proxy.
- Set a strong `API_KEY`; do not expose anonymous parsing publicly.
- Restrict `CORS_ORIGINS` to the deployed UI.
- Apply infrastructure rate and body-size limits in addition to application controls.
- Monitor model spend, latency, 4xx/5xx rates, and repeated rejected uploads.
- Review OpenAI retention and regional terms for the document sensitivity involved.

## Residual risks

Document content can contain adversarial instructions, malformed structures, decompression
bombs, or sensitive data. Validation and bounded processing reduce but cannot eliminate
parser and model risk. Grounded output supports review but is not a correctness guarantee.
Consequential extraction should retain human verification.
