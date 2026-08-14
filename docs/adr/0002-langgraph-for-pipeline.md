# ADR 0002 — Direct bounded page processing

## Status

Original graph/queue design superseded; current decision accepted for Paperplane 4.1.0
(2026-08-14).

## Context

Earlier versions coordinated durable jobs and page work through service, queue, database,
and graph-oriented abstractions. Version 4 removed those systems in favor of one local,
synchronous extraction workspace.

## Decision

`AgenticDocumentParser` orchestrates document pages directly in Python. Native content uses
Docling. Scans and images use `V2PageProcessor`, whose Luna and Terra work is bounded by the
selected Fast, Balanced, or Audit policy.

The active path is explicit:

```text
validate -> inspect -> route -> parse -> ground -> optional verify -> assemble
```

There is no LangGraph runtime, durable page lease, database checkpoint, worker queue, or
autonomous agent loop.

## Consequences

- One parse completes synchronously in the Streamlit session.
- Vision pages are processed sequentially and cannot resume after interruption.
- Model work remains schema-constrained and bounded.
- Adding durable or distributed execution requires a new ADR and product-scope decision.
