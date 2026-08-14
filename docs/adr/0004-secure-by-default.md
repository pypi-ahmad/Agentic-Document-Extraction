# ADR 0004 — Secure local boundary

## Status

Original hosted HTTP-boundary decision superseded; revised for Paperplane 5.0.0
(2026-08-14).

## Context

Paperplane no longer exposes a FastAPI service or public network API. Its trust boundary is
a localhost Streamlit process that accepts untrusted documents and can send selected visual
content to the selected model provider endpoint.

## Decision

- Bind Streamlit to `127.0.0.1`; do not advertise a public deployment.
- Keep XSRF protection enabled and Streamlit usage telemetry disabled.
- Validate extension, integrity, size, pages, PDF canvas, decoded pixels, and encryption.
- Keep active UI objects in session memory; retain job metadata and private artifacts only
  under `%LOCALAPPDATA%\Paperplane` with a seven-day TTL and explicit deletion controls.
- Never persist credentials or raw provider authorization material.
- Never inspect pages outside the selected range or share context between uploaded files.
- Block Agnes private visual processing while its interface requires public image URLs.
- Read secrets from environment variables or ignored local configuration; never print them.
- Sanitize model-produced Markdown before rendering supported HTML.
- Bound upstream timeouts and model work by processing mode.
- Show safe errors without raw provider payloads or document content.

## Consequences

- Local single-user operation is the only supported deployment.
- Scans, images, and requested figure crops leave the machine for the configured provider.
- A shared or internet-facing deployment requires a new threat model, authentication,
  authorization, TLS, retention, isolation, monitoring, and abuse controls.
