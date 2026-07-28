# Fix Agentic V2 Pipeline Review Findings

## Task 1: Fix dpt_api.py router prefix so the app is reachable end-to-end

**Description:** `backend/app/routers/dpt_api.py:58` mounts `router = APIRouter(prefix="/v2", ...)`.
Every other router in the app (`v2_jobs.py`, `extraction_schemas.py`, `ollama_models.py`) uses
`/api/...`, and `docs/ARCHITECTURE.md:45` documents `/api/*` as the only path
`frontend/next.config.js` proxies to the backend. Change the prefix to `/api/v2` and update every
place that assumes the old bare path (tests, docs, scripts).

**Acceptance criteria:**
- [ ] `dpt_api.py` router prefix is `/api/v2`
- [ ] All routes under it (`/parse`, `/parse/jobs`, `/extract`, `/extract/jobs`, etc.) resolve at
      `/api/v2/...`
- [ ] No remaining reference to the bare `/v2/...` path in backend code, tests, or docs

**Verification:**
- [ ] `uv run pytest backend/tests/unit/test_dpt_api.py -q` passes
- [ ] `uv run pytest -q` (full backend suite) passes
- [ ] Grep confirms no leftover bare-`/v2` references: `grep -rn "prefix=\"/v2\"\|'/v2/parse\|\"/v2/parse" backend frontend docs`

**Dependencies:** None — do this first, everything else is unreachable until it lands.

**Files likely touched:**
- `backend/app/routers/dpt_api.py`
- `backend/tests/unit/test_dpt_api.py`
- `frontend/src/lib/api.ts` (only if paths there were written assuming the bug, e.g. missing an
  extra `/api` segment)

**Estimated scope:** XS (1-2 files, one-line prefix change + reference cleanup)

---

## Task 2: Table cells get correct row/col instead of fabricated values

**Description:** `backend/app/services/v2_worker.py:234-235` (`_agentic_page`) emits every table
cell with `row=0` hardcoded and `col=cell_index`, a flat enumeration over all cells regardless of
which row they're actually in. `GroundedChunk` (`v2_contracts.py`) has no row/col field, so there
is currently no real data to read. **Start with the investigation sub-step before writing code:**
check whether the Luna/Terra model's raw draft or reconciliation JSON (`PAGE_DRAFT_SCHEMA` in
`v2_pipeline.py`) already includes row/col-like structure that's being discarded when `GroundedChunk`
is built. If yes, thread it through. If no, derive row/col deterministically from cell bounding-box
geometry: cluster cells into rows by `top` (with a tolerance band), then assign `col` by sort order
of `left` within each row.

**Acceptance criteria:**
- [ ] A table with 2+ rows produces `AgenticBlockInput` cells whose `row` value differs across
      rows (not all zero)
- [ ] `col` values restart per row rather than incrementing flatly across the whole table
- [ ] Existing single-row-table behavior is unchanged

**Verification:**
- [ ] New unit test in `backend/tests/unit/test_v2_worker.py` builds a synthetic multi-row
      `PageResult` and asserts correct row/col assignment
- [ ] `uv run pytest backend/tests/unit/test_v2_worker.py -q` passes
- [ ] `uv run pytest -q` (full backend suite) passes

**Dependencies:** None (independent of Task 1, but confirm Task 1's prefix fix hasn't landed
conflicting changes in the same file first).

**Files likely touched:**
- `backend/app/services/v2_worker.py`
- Possibly `backend/app/services/parsing/v2_contracts.py` (`GroundedChunk`) and
  `backend/app/services/parsing/v2_pipeline.py` (`PAGE_DRAFT_SCHEMA`) if the model-output-threading
  approach is chosen instead of the geometry heuristic
- `backend/tests/unit/test_v2_worker.py`

**Estimated scope:** S if geometry heuristic; M if it requires threading new fields through the
model schema and `GroundedChunk`. Report back after the investigation step which path this needs.

---

## Task 3: Fix draft-chunk matching boosting candidates with unparseable boxes

**Description:** `backend/app/services/parsing/v2_pipeline.py:602-608` — the `max()` key function
is `overlap_over_smaller_area(box, _parse_model_box(candidate.get("box")) or box)`. When a
candidate's box fails to parse, substituting `box` (the target's own box) makes the overlap
score 1.0 — the maximum possible — so a chunk with a broken box always wins over a legitimately
positioned one. Exclude unparseable-box candidates from the `max()` pool instead of substituting
a synthetic perfect score.

**Acceptance criteria:**
- [ ] A `draft_raw_chunks` list containing one candidate with an unparseable box and one with a
      genuinely well-overlapping valid box selects the valid one
- [ ] If every candidate has an unparseable box, behavior degrades gracefully (falls back to
      `matched = raw`, matching the existing "no draft chunks" path) rather than crashing on an
      empty sequence passed to `max()`

**Verification:**
- [ ] New unit test in `backend/tests/unit/test_v2_page_processor.py` reproducing the failure
      scenario (malformed-box candidate present) and asserting the correct chunk is matched
- [ ] `uv run pytest backend/tests/unit/test_v2_page_processor.py -q` passes
- [ ] `uv run pytest -q` (full backend suite) passes

**Dependencies:** None.

**Files likely touched:**
- `backend/app/services/parsing/v2_pipeline.py`
- `backend/tests/unit/test_v2_page_processor.py`

**Estimated scope:** S (1-2 files, isolated logic change)

---

## Task 4: Fix parent_order remap after figure-group merge shifts positions

**Description:** `backend/app/services/parsing/v2_pipeline.py:274-309` (`_merge_figure_groups`)
inserts/pops chunks, shifting every subsequent chunk's position, but only nulls `parent_order`
values that are now out of range (`parent >= index`) — it never remaps values that still look
numerically valid after the shift, so they can end up pointing at the wrong chunk (e.g. the newly
inserted figure specialist). `_merge_reconciled_chunks` already solves the equivalent problem with
explicit position-remap tables (`terra_positions`/`draft_positions`); apply the same approach here.

**Acceptance criteria:**
- [ ] A table cell's `parent_order` still points at its actual parent table after a figure group
      is inserted/merged before it in the chunk list
- [ ] Existing figure-merge behavior (dedup by overlap, insertion at correct reading-order position)
      is unchanged

**Verification:**
- [ ] New unit test in `backend/tests/unit/test_v2_page_processor.py` constructing a chunk list
      where a figure-group merge shifts a table cell's true parent, asserting `parent_order` still
      resolves correctly after the merge
- [ ] `uv run pytest backend/tests/unit/test_v2_page_processor.py -q` passes
- [ ] `uv run pytest -q` (full backend suite) passes

**Dependencies:** None (touches the same file as Task 3 — land sequentially, not in parallel, to
avoid merge conflicts in the same function neighborhood).

**Files likely touched:**
- `backend/app/services/parsing/v2_pipeline.py`
- `backend/tests/unit/test_v2_page_processor.py`

**Estimated scope:** S-M

---

## Task 5: Evaluation raises a clean 4xx on page-count mismatch

**Description:** `backend/app/services/parsing/v2_evaluation.py:57-61` loops
`range(1, predicted.page_count + 1)` and indexes `labels.pages[page_number - 1]` without checking
`labels.source.page_count == predicted.source.page_count` first. An uploaded labels file with fewer
pages than the prediction raises an unhandled `IndexError`, surfacing as a 500 instead of the clean
`invalid_evaluation_labels` 4xx the surrounding `except ValueError` block is clearly meant to
produce. Add an explicit page-count check that raises `ValueError` up front.

**Acceptance criteria:**
- [ ] Calling `evaluate_grounded_document` with a `labels` document whose `page_count` differs
      from `predicted`'s raises `ValueError` (not `IndexError`)
- [ ] The existing 4xx path in `backend/app/routers/v2_jobs.py` (`evaluate_v2_job`) turns this into
      the same `invalid_evaluation_labels` response it already produces for other validation
      failures

**Verification:**
- [ ] New unit test in `backend/tests/unit/test_v2_evaluation.py` with mismatched page counts,
      asserting `ValueError` (not `IndexError`)
- [ ] `uv run pytest backend/tests/unit/test_v2_evaluation.py -q` passes
- [ ] `uv run pytest -q` (full backend suite) passes

**Dependencies:** None.

**Files likely touched:**
- `backend/app/services/parsing/v2_evaluation.py`
- `backend/tests/unit/test_v2_evaluation.py`

**Estimated scope:** XS

---

## Task 6: Frontend document preview uses apiResourceUrl() for source_preview_url

**Description:** `frontend/src/app/page.tsx:131` passes `active.source_preview_url` straight to
`DocumentCanvas`'s `fetch`, bypassing the `apiResourceUrl()` wrapper every other artifact URL in
the codebase goes through to add the required `/api` prefix. Breaks the preview on reload or when
selecting a run from `RunHistory` (the normal flow, not just first-submit-in-session). Import
`apiResourceUrl` from `@/lib/api` and wrap it; drop the now-dead `?? backtick-fallback` since
`source_preview_url` is a required non-optional field.

**Acceptance criteria:**
- [ ] `source_preview_url` is passed through `apiResourceUrl()` before use
- [ ] Dead fallback expression removed
- [ ] Document preview loads after a page reload and after selecting a prior run from
      `RunHistory`, not just immediately after upload

**Verification:**
- [ ] `frontend/src/app/page.test.tsx` covers (or gains a case covering) preview URL construction
- [ ] `npm test` (frontend suite) passes
- [ ] Manual check: reload the app with an existing job selected, confirm the source preview loads
      (no 404 in network tab)

**Dependencies:** None. Best landed after Task 1 (router prefix fix) so manual verification exercises
the real, now-working proxy path rather than masking one bug with another.

**Files likely touched:**
- `frontend/src/app/page.tsx`
- `frontend/src/app/page.test.tsx`

**Estimated scope:** XS

---

## Task 7: Fix duplicate-sibling substring-containment false positive

**Description:** The duplicate-sibling check in `backend/app/services/parsing/v2_evaluation.py`
(`_has_duplicate_siblings`) flags two top-level items as duplicates using substring containment
(`first_text in second_text or second_text in first_text`) rather than equality. A short sibling
like a page-number item `"1"` false-positives against an unrelated heading `"1. Introduction"`,
zeroing `duplicate_sibling_score` for a well-formed document. Switch to exact match (post-
normalization), or a length-ratio-gated similarity check consistent with how
`v2_reconciliation.py`'s `suppress_duplicate_chunks` already handles this exact problem.

**Acceptance criteria:**
- [ ] A document containing both a short numeric/label item and an unrelated longer heading that
      happens to contain it as a substring does not get flagged as having duplicate siblings
- [ ] Genuine duplicate siblings (same normalized text) are still flagged

**Verification:**
- [ ] New unit test in `backend/tests/unit/test_v2_evaluation.py` with the short-substring false
      positive scenario, asserting no duplicate flag
- [ ] Existing duplicate-detection tests still pass
- [ ] `uv run pytest -q` (full backend suite) passes

**Dependencies:** None. Can land alongside Task 5 (same file) or after — sequence to avoid merge
conflicts if done in the same session.

**Files likely touched:**
- `backend/app/services/parsing/v2_evaluation.py`
- `backend/tests/unit/test_v2_evaluation.py`

**Estimated scope:** S

---

## Task 8: Decide fate of dead backend/app/routers/v2_jobs.py — human decision required

**Description:** `main.py` now mounts `dpt_api_router` where it used to mount `v2_jobs_router`
(prefix `/api/v2/jobs`), so the old router's routes are unreachable in the running app. Only its
own test file (`test_v2_api.py`, mounted on a throwaway `FastAPI()` instance) still exercises it.
Yet this diff kept editing `v2_jobs.py` (added `preview_url`, `/source` route) as if it were live.
This is not a task to execute autonomously — confirm with the human first whether the old
`/api/v2/jobs/*` surface is fully superseded (delete the router, its test, and any exclusively-
supporting code) or whether dropping it from `main.py` was accidental and it needs to be remounted
alongside `dpt_api_router`.

**Acceptance criteria:**
- [ ] Human has explicitly chosen "delete" or "remount"
- [ ] If delete: `v2_jobs.py`, `test_v2_api.py`, and any code that exists solely to support them
      are removed; confirm via grep that nothing else imports from `app.routers.v2_jobs`
- [ ] If remount: `main.py` includes both routers; confirm no route-path collisions between
      `/api/v2/jobs/*` and `/api/v2/*` (post Task 1 prefix fix)

**Verification:**
- [ ] `uv run pytest -q` (full backend suite) passes either way
- [ ] `grep -rn "routers.v2_jobs" backend` shows no references if deleted

**Dependencies:** Task 1 must land first (so the "remount" option's path collision check is against
the corrected `/api/v2` prefix, not the buggy bare `/v2` one).

**Files likely touched:**
- `backend/app/main.py`
- `backend/app/routers/v2_jobs.py` (deleted or kept)
- `backend/tests/unit/test_v2_api.py` (deleted or kept)

**Estimated scope:** XS once the human decision is made — this task is blocked on that decision,
not on implementation effort.
