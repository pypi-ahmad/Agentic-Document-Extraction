# Balanced PDF Latency Design

## Goal

Process a cold-cache, 10-page PDF in Balanced mode within 180 seconds while preserving
the public `document.md` and `document.json` artifacts and avoiding a material extraction
accuracy regression.

Audit mode remains accuracy-first and is outside this latency target.

## Current bottleneck

The V2 queue already processes four pages concurrently. Within a page, however, optional
Terra reconciliation and crop verification are coordinated procedurally, and independent
crop checks are awaited serially. A difficult page can therefore accumulate several model
round trips and dominate document latency.

The existing database-backed page leases remain the correct document-level durability
boundary. Replacing them with LangGraph persistence would duplicate queueing, recovery,
and idempotency logic.

## Design

Add a small LangGraph workflow inside page processing:

1. Draft the page with Luna.
2. Compute deterministic quality signals.
3. Route directly to finalization when the draft is sufficient.
4. Otherwise run full-page Terra reconciliation when the Balanced policy requires it.
5. Fan out only independent precision/crop checks with LangGraph `Send` workers.
6. Reduce worker results in stable reading order and finalize the page.

The graph is a deterministic workflow, not an autonomous agent loop. Model calls act as
specialist workers with strict schemas and bounded retries. The existing `V2PageTaskRunner`
continues to lease, cache, persist, and assemble pages.

## Concurrency and deadline

- Retain the existing document-level `v2_worker_count` default of four.
- Bound crop-worker fan-out so combined page and crop concurrency cannot grow without
  limit. LangGraph invocation supplies `max_concurrency`.
- Balanced jobs receive a 170-second processing budget, reserving 10 seconds for page
  persistence and document assembly.
- Before starting optional reconciliation or repair work, check the remaining budget.
- If the budget is exhausted, finalize the best Luna/native-text result already available.
  Content is preserved and marked with a concise deadline fallback warning.
- In-flight required calls use the existing HTTP timeout. Optional calls are not launched
  when their budget is unavailable.

This is a completion deadline, not a promise that every optional verification pass will
run during provider degradation.

## Accuracy safeguards

- Native-text exact matches remain authoritative.
- Critical identifiers, empty form fields, and unresolved content retain precision routing
  while budget remains.
- Deadline fallback never replaces extracted text with an empty warning placeholder.
- Results are reduced by original chunk order, so concurrency cannot reorder output.
- Audit behavior is unchanged.

## Observability

Record structured fields at page boundaries:

- mode and prompt version;
- page and stage latency;
- model and reasoning effort;
- model-call count and token usage;
- cache hit;
- reconciliation/crop counts;
- deadline fallback status.

No document text or credentials are logged.

## Verification

1. Unit-test graph routing, bounded fan-out, stable reduction, and deadline fallback.
2. Run the existing V2 unit suite and lint checks.
3. Run a cold-cache Balanced benchmark against
   `C:\Users\ahmad\OneDrive\Desktop\PublicWaterMassMailing.pdf`.
4. Compare the generated Markdown with LandingAI and LlamaParse references.
5. Run or construct a representative 10-page benchmark and require wall time at or below
   180 seconds.

The latency gate passes only on a cold application cache. Accuracy must not materially
regress from the current Balanced baseline; strict accuracy and token F1 are reported with
the timing result.

## Scope

Expected changes are limited to the V2 page pipeline, one small workflow module, relevant
configuration/worker integration, tests, and the existing benchmark script. No new package,
queue replacement, UI redesign, or general multi-agent framework is introduced.
