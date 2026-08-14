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
Docling. Scans and images use `V2PageProcessor` with the selected provider adapter. OpenAI
maps work to Luna/Terra; Agnes maps every model call to `agnes-2.5-flash`. Fast, Balanced,
and Audit bound the work for either provider.

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
