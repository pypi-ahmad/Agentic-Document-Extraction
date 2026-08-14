# Archived plan: Balanced PDF latency

## Status

Superseded by the local Streamlit runtime on 2026-08-14. Do not execute the former
FastAPI, database lease, worker queue, LangGraph, persistence, or job-deadline tasks.

## Original intent

The plan targeted a cold-cache 10-page Balanced PDF under 180 seconds while preserving
content quality. It assumed a durable four-worker page queue and proposed a page-local
LangGraph workflow with a shared job deadline.

## Current v4.2.1 design

- `AgenticDocumentParser` runs synchronously in the Streamlit session.
- Vision pages are processed sequentially.
- Fast skips verification, Balanced verifies flagged work, and Audit uses the largest budget.
- Each selected-provider client uses a 180-second request timeout.
- There is no document SLA, queue, worker concurrency, durable job, resume, or cache replay.
- Successful page content uses bounded fallbacks rather than an autonomous retry loop.

## Current performance guidance

Measure end-to-end wall time with representative local documents and pinned versions.
Report input type, pages, mode, provider latency, and result quality together. Do not claim
the archived 180-second document target as a current guarantee.

Any future concurrency or deadline work must preserve reading order, bounded model calls,
session-only state, and evidence quality, with tests added before implementation.
