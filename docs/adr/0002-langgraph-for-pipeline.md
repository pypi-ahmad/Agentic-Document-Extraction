# ADR 0002 — LangGraph over a bespoke orchestrator

## Status

Accepted (2026-06-22).

## Context

The extraction pipeline is a four-node state machine: `parse`,
`extract`, `validate`, `finalize`. The alternative to LangGraph was
a hand-rolled async orchestrator on top of `asyncio.Task`.

## Decision

We use LangGraph 1.x.

## Rationale

- **First-class state model.** The `TypedDict` + `Annotated` reducer
  pattern makes it obvious which fields are inputs, which are
  outputs, and which are global. The bespoke alternative needs a
  parallel convention that the team has to discover.
- **Streaming.** `astream(stream_mode="updates")` gives us per-node
  updates with no boilerplate. The bespoke alternative would
  reinvent this poorly.
- **Observability hooks.** LangSmith tracing is opt-in but
  available; we may turn it on later without code changes.
- **Hiring.** LangGraph is widely adopted; the on-ramp for a new
  contributor is shorter than for a custom framework.

## Consequences

- The pipeline is bound to the LangGraph version in `uv.lock`.
  Upgrades are reviewed separately.
- The bespoke `_run_extraction_pipeline` driver in
  `app/routers/extractions.py` translates the LangGraph stream
  into per-step DB rows. That translation is the only place
  LangGraph leaks into the rest of the codebase.
