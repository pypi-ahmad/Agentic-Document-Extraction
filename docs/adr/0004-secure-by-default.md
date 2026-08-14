# ADR 0004 — Secure-by-default HTTP boundary

## Status

Accepted; updated for stateless V2 (2026-08-14).

## Decision

- Validate document type, signature, size, page count, and decoded pixels.
- Send security headers on every response.
- Allow only exact configured browser origins.
- Support backend-only `X-API-Key` authentication and request throttling.
- Bound model calls and upstream timeouts.
- Do not persist source documents or responses.

Internet deployments still require TLS, a strong API key, proxy-level limits, monitoring,
and an explicit model-provider privacy policy.
