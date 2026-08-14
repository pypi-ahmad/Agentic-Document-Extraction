# Paperplane V2 assurance architecture

V2 validates and preflights an upload, snapshots a versioned recipe, leases independent
page tasks, drafts each page with Luna, and spends a bounded Terra budget only on decisions
that need reconciliation or crop verification. V9 caps Balanced at two Terra calls/one
crop and Audit at six Terra calls/five crops. `V2_RECIPE_VERSION=v8` is the rollback.

Every page writes a sanitized call record and content-addressed page/crop evidence. Final
assembly emits the unchanged public document contract plus a tamper-evident audit manifest
and private evidence ZIP. Credentials, request headers, and base64 image payloads are never
recorded. If some pages exhaust retries, successful pages still assemble with explicit
failed-page metadata; all-page failure remains terminal.

The DPT-compatible response remains intact. Job resources add assurance state, page state,
and a compact timeline for the UI. See [ARCHITECTURE.md](ARCHITECTURE.md) for the broader
service layout.
