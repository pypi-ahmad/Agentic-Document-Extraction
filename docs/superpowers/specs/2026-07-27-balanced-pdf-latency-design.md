# Archived design: Balanced PDF latency

## Status

Superseded by the synchronous Streamlit pipeline on 2026-08-14.

## Historical design

The design proposed a 170-second shared job budget, four database-leased page workers,
LangGraph crop fan-out, persistent page state, and a 180-second 10-page document target.
Those assumptions no longer exist in Paperplane.

## Current design

Balanced mode uses Luna drafting, deterministic quality signals, Terra reconciliation for
flagged content, and bounded crop verification. Vision pages run sequentially. The OpenAI
client has a 180-second request timeout, but Paperplane does not publish a document-level
latency SLA.

Required invariants remain:

- preserve native text authority and critical identifiers;
- never replace useful content with an empty timeout placeholder;
- keep output in source reading order;
- bound model calls and repairs; and
- never log document text or credentials.

Future performance work requires current-code profiling, locked representative fixtures,
quality comparisons, and a new plan based on the database-free runtime.
