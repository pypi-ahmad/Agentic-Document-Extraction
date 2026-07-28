# Implementation Plan: Fix Agentic V2 Pipeline Review Findings

## Overview

The agentic extraction pipeline (`backend/app/routers/dpt_api.py`, `backend/app/services/agentic/*`,
`backend/app/services/parsing/v2_pipeline.py`, `backend/app/services/v2_worker.py`) was merged
directly to `main` and code-reviewed after the fact. The review found one bug that makes the
entire feature unreachable through the real app (frontend -> Next.js -> FastAPI), one bug that
fabricates table geometry, and several narrower correctness/architecture issues. This plan fixes
them as small, independently verifiable, vertically-sliced tasks.

## Architecture Decisions

- Every backend route must live under `/api/...` — this is the documented contract
  (`docs/ARCHITECTURE.md:45`) and the only path `frontend/next.config.js` proxies to the backend.
  `dpt_api.py` is the one router that violates it; fix at the source (router prefix), not by
  special-casing the frontend client.
- Table row/col cannot be fixed inside `v2_worker.py` alone: `GroundedChunk`
  (`backend/app/services/parsing/v2_contracts.py`) carries no row/col concept, so
  `_agentic_page` has nothing real to read. The fix must either (a) thread row/col through from
  the model's raw draft/reconciliation output if the model already returns it, or (b) derive it
  deterministically from cell bounding-box geometry (cluster by `top`, order by `left`) if the
  model does not. Task 2 starts with a short investigation step to pick between these before
  writing code, since guessing wrong means redoing the data model change.
- Each fix ships with a regression test reproducing the original failure mode — the review
  found these because no existing test exercised the broken path.
- No fix in this plan changes the public agentic API response shape except where the bug *is*
  the response shape (row/col values).

## Task List

### Phase 1: Unblock the feature (Critical, do first — everything else is unreachable until this lands)

- [ ] Task 1: Fix `dpt_api.py` router prefix so the app is reachable end-to-end

### Checkpoint: Phase 1
- [ ] `uv run pytest` backend suite green
- [ ] Manually confirm (or agent confirms via curl/browser) `POST /api/v2/parse` reaches the
      backend through the Next.js dev proxy, not just via direct ASGI test client

### Phase 2: Correctness fixes (Critical/Required, independent of each other — parallelizable)

- [ ] Task 2: Table cells get correct row/col instead of fabricated `row=0`/flat index
- [ ] Task 3: Fix draft-chunk matching boosting candidates with unparseable boxes
- [ ] Task 4: Fix `parent_order` remap after figure-group merge shifts chunk positions
- [ ] Task 5: Evaluation raises a clean 4xx on page-count mismatch instead of `IndexError` -> 500
- [ ] Task 6: Frontend document preview uses `apiResourceUrl()` for `source_preview_url`

### Checkpoint: Phase 2
- [ ] `uv run pytest` backend suite green (new regression tests included)
- [ ] `npm test` frontend suite green
- [ ] Review with human before Phase 3

### Phase 3: Lower-severity cleanup (Required, cosmetic-adjacent — can slip if time-boxed)

- [ ] Task 7: Fix duplicate-sibling substring-containment false positive in evaluation
- [ ] Task 8: Decide fate of dead `backend/app/routers/v2_jobs.py` (delete vs. deliberately
      remount) — **human decision required**, not an autonomous deletion

### Checkpoint: Complete
- [ ] All acceptance criteria met
- [ ] Full backend + frontend suites green
- [ ] `git diff` reviewed per task, no unrelated changes mixed in

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Task 1's prefix change breaks any external caller already depending on bare `/v2/...` | Low — feature never worked through the real stack, so no real external caller exists yet | Grep the whole repo (frontend, scripts, docs) for the old path before landing |
| Task 2's real fix scope is larger than expected if the model doesn't return row/col at all | Medium — could require a schema/prompt change to `PAGE_DRAFT_SCHEMA`, not just worker code | Investigation sub-step decides approach before implementation; report back if schema change is needed rather than silently picking the geometry-heuristic fallback |
| Fixing Task 3/4 changes reconciliation output for pages already processed | Low — no persisted "golden" outputs depend on the current buggy behavior; covered by existing + new tests | Run full `test_v2_page_processor.py` suite (937 lines) after each change |
| Task 8 deletion removes something still relied on outside this repo | Unknown | Do not delete without explicit human confirmation |

## Open Questions

- Task 2: does the Luna/Terra model output already include row/col-like signals in its raw JSON
  (check `PAGE_DRAFT_SCHEMA` in `v2_pipeline.py` and a sample raw response) before assuming a
  geometry-clustering heuristic is required?
- Task 8: is `backend/app/routers/v2_jobs.py`'s `/api/v2/jobs/*` surface fully superseded by the
  new `/api/v2/parse/jobs` surface, or was dropping it from `main.py` an accident that also needs
  a frontend audit beyond `api.ts` (e.g. any hardcoded fetch calls, external integrations, docs)?
