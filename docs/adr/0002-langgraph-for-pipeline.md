# ADR 0002 — Direct bounded page processing

## Status

Original graph/queue design superseded; revised for Paperplane 5.0.0 (2026-08-14).

## Context

Earlier versions used service, queue, and graph-oriented abstractions. Version 5 keeps
direct bounded page orchestration while adding a small local SQLite lifecycle/checkpoint
service; it does not restore distributed workers or an autonomous graph runtime.

## Decision

`AgenticDocumentParser` orchestrates document pages directly in Python. Native content uses
Docling. Scans and images use `V2PageProcessor` with the selected provider adapter. The
selected catalog model handles drafting and any verification calls. Fast, Balanced, and
Audit bound the work for every provider.

The active path is explicit:

```text
validate -> inspect -> route -> parse -> ground -> optional verify -> assemble
```

There is no LangGraph runtime, page lease, distributed worker queue, or autonomous agent
loop. `JobStore` and `DurableJobService` persist local status, artifacts, and atomic
checkpoints so interrupted work is discoverable and future HTTP wrapping does not leak into
the parser.

## Consequences

- One parse computes inside the Streamlit process while files run concurrently.
- Selected pages remain ordered. Checkpoints survive restart, but compute resumes only
  while the local app is running.
- Model work remains schema-constrained and bounded.
- Adding distributed execution or an HTTP API requires a new ADR and product-scope decision.
