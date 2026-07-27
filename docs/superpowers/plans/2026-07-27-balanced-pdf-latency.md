# Balanced PDF Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete a cold-cache 10-page PDF in Balanced mode within 180 seconds by using a bounded LangGraph workflow for optional page verification while preserving extracted content.

**Architecture:** Keep the existing database-leased four-worker page queue as the durable document orchestrator. Add one stateless LangGraph page workflow that conditionally reconciles flagged pages and fans independent crop checks out through `Send`; enforce one shared 170-second Balanced job deadline and finalize available Luna/native content when optional work cannot start in time.

**Tech Stack:** Python 3.12, asyncio, LangGraph 1.2, FastAPI service code, Pydantic 2, SQLAlchemy asyncio, PyMuPDF, pytest, uv.

## Global Constraints

- The 180-second SLA applies only to cold-cache Balanced processing; Audit remains accuracy-first.
- Reserve 10 seconds of the SLA for persistence and assembly, leaving a 170-second processing deadline.
- Preserve exactly two public artifacts: `document.md` and `document.json`.
- Do not add a dependency, replace the durable page queue, or introduce autonomous agent loops.
- Preserve native-text authority, critical-identifier verification, stable reading order, and non-empty fallback content.
- Never log document text, credentials, or raw PII.
- Preserve all unrelated dirty-worktree changes.

---

### Task 1: Shared Balanced Job Deadline

**Files:**
- Modify: `backend/app/config.py:47-54`
- Modify: `backend/app/services/v2_worker.py:126-168`
- Modify: `backend/app/services/parsing/v2_pipeline.py:365-399`
- Test: `backend/tests/unit/test_v2_worker.py`
- Test: `backend/tests/unit/test_v2_page_processor.py`

**Interfaces:**
- Produces: `Settings.balanced_processing_deadline_seconds: float` with default `170.0`.
- Produces: an optional `deadline_at: datetime | None = None` keyword on the existing `V2PageProcessor.process_page` signature; return type remains `PageResult`.
- Consumes: existing `ParseJob.started_at`; no migration or new database column.

- [ ] **Step 1: Write failing configuration and runner tests**

Add a settings assertion and extend the existing fake processor in `test_v2_worker.py` to capture `deadline_at`. Create a Balanced job with `started_at=None`, run one page, and assert that the runner passes a timezone-aware deadline approximately 170 seconds after the stored `started_at`:

```python
assert Settings().balanced_processing_deadline_seconds == 170.0
assert fake_processor.deadline_at is not None
assert fake_processor.deadline_at.tzinfo is not None
assert 169 <= (fake_processor.deadline_at - job.started_at).total_seconds() <= 171
```

Add a processor contract test proving Audit receives no deadline when the caller omits it:

```python
result = await V2PageProcessor(adapter).process_page(
    source=b"pdf",
    filename="sample.pdf",
    source_sha256="a" * 64,
    page=page,
    mode=ProcessingMode.AUDIT,
)
assert result.markdown
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_worker.py backend/tests/unit/test_v2_page_processor.py -q
```

Expected: FAIL because the setting and `deadline_at` parameter do not exist.

- [ ] **Step 3: Add the setting and establish the deadline once per job**

Add to `Settings`:

```python
balanced_processing_deadline_seconds: float = Field(default=170.0, gt=0, le=170.0)
```

In `V2PageTaskRunner.run`, lock the job row while establishing `started_at`, then derive one UTC deadline shared by every page:

```python
job = await session.scalar(
    select(ParseJob)
    .where(ParseJob.id == task.job_id)
    .with_for_update()
    .options(selectinload(ParseJob.pages))
)
if job.started_at is None:
    job.started_at = dt.datetime.now(dt.UTC)
deadline_at = (
    job.started_at + dt.timedelta(seconds=settings.balanced_processing_deadline_seconds)
    if mode == ProcessingMode.BALANCED
    else None
)
```

Pass `deadline_at=deadline_at` to `process_page`. Add the optional keyword to `V2PageProcessor.process_page`; do not change Audit or Economy callers.

- [ ] **Step 4: Run focused tests and lint**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_worker.py backend/tests/unit/test_v2_page_processor.py -q
uv run ruff check backend/app/config.py backend/app/services/v2_worker.py backend/app/services/parsing/v2_pipeline.py backend/tests/unit/test_v2_worker.py backend/tests/unit/test_v2_page_processor.py
```

Expected: PASS.

- [ ] **Step 5: Commit the deadline boundary**

```powershell
git add backend/app/config.py backend/app/services/v2_worker.py backend/app/services/parsing/v2_pipeline.py backend/tests/unit/test_v2_worker.py backend/tests/unit/test_v2_page_processor.py
git diff --staged
git commit -m "perf: bound balanced document processing time"
```

---

### Task 2: Stateless LangGraph Page Workflow

**Files:**
- Create: `backend/app/services/parsing/v2_page_workflow.py`
- Create: `backend/tests/unit/test_v2_page_workflow.py`

**Interfaces:**
- Produces: `VerificationJob` and `VerificationResult` typed dictionaries with an integer `order`.
- Produces: `PageWorkflowCallbacks` dataclass containing async `draft`, `reconcile`, `plan_verifications`, `verify`, and `finalize` callables.
- Produces: `run_page_workflow(callbacks, *, deadline_at, max_concurrency) -> PageResult`.
- The graph is compiled without a checkpointer because database page leases already provide persistence.

- [ ] **Step 1: Write failing graph routing tests**

Create three async tests using callback fakes:

```python
async def test_clean_page_skips_reconciliation_and_verification():
    calls = []
    result = await run_page_workflow(
        callbacks(clean=True, calls=calls), deadline_at=None, max_concurrency=2
    )
    assert calls == ["draft", "finalize"]
    assert result.markdown == "clean"


async def test_flagged_page_reconciles_then_verifies_in_stable_order():
    result = await run_page_workflow(
        callbacks(clean=False, verification_orders=[3, 1, 2]),
        deadline_at=None,
        max_concurrency=2,
    )
    assert [item.order for item in result.verifications] == [1, 2, 3]


async def test_expired_deadline_skips_optional_nodes():
    calls = []
    result = await run_page_workflow(
        callbacks(clean=False, calls=calls),
        deadline_at=datetime.now(UTC) - timedelta(seconds=1),
        max_concurrency=2,
    )
    assert calls == ["draft", "finalize"]
    assert result.deadline_fallback is True
```

Use an `asyncio.Lock` counter in the verification fake and assert peak concurrency is exactly two when three jobs are supplied.

- [ ] **Step 2: Run the new test and verify failure**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_page_workflow.py -q
```

Expected: FAIL because `v2_page_workflow` does not exist.

- [ ] **Step 3: Implement the minimal workflow**

Use `StateGraph`, `Send`, and an additive reducer:

```python
class PageWorkflowState(TypedDict, total=False):
    draft: object
    flagged: bool
    reconciled: object
    verification_jobs: list[VerificationJob]
    verifications: Annotated[list[VerificationResult], operator.add]
    deadline_fallback: bool
    result: PageResult


def optional_work_available(deadline_at: datetime | None) -> bool:
    return deadline_at is None or datetime.now(UTC) < deadline_at
```

Build edges `START -> draft`, route clean/expired pages to `finalize`, route flagged pages to `reconcile`, then `plan_verifications`. Return one `Send("verify", {"job": job})` per job; every verification result includes `order`. Route an empty job list directly to `finalize`. In `finalize`, sort reducer output by `order` before calling the callback.

Invoke with:

```python
await graph.ainvoke({}, config={"max_concurrency": max_concurrency})
```

Do not configure LangGraph persistence or retries. Existing HTTP handling and page leases own those concerns.

- [ ] **Step 4: Run graph tests and lint**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_page_workflow.py -q
uv run ruff check backend/app/services/parsing/v2_page_workflow.py backend/tests/unit/test_v2_page_workflow.py
```

Expected: PASS, including bounded peak concurrency and stable ordering.

- [ ] **Step 5: Commit the isolated workflow**

```powershell
git add backend/app/services/parsing/v2_page_workflow.py backend/tests/unit/test_v2_page_workflow.py
git diff --staged
git commit -m "perf: add bounded page verification workflow"
```

---

### Task 3: Route V2 Page Processing Through the Workflow

**Files:**
- Modify: `backend/app/services/parsing/v2_pipeline.py:365-756`
- Modify: `backend/app/services/parsing/v2_contracts.py:45-79`
- Test: `backend/tests/unit/test_v2_page_processor.py`

**Interfaces:**
- Consumes: `run_page_workflow` and `PageWorkflowCallbacks` from Task 2.
- Produces: `ModePolicy.crop_concurrency: int`; Balanced is `2`, Audit is `1`, Economy is `1`.
- Preserves: `V2PageProcessor.process_page` return type and all public output contracts.

- [ ] **Step 1: Add failing integration tests**

Add a delayed adapter that records active `crop_verification_v7` calls. Provide one flagged Balanced draft with three independent disagreements and assert:

```python
result = await processor.process_page(
    source=source,
    filename="scan.pdf",
    source_sha256="b" * 64,
    page=page,
    mode=ProcessingMode.BALANCED,
    deadline_at=datetime.now(UTC) + timedelta(seconds=30),
)
assert adapter.peak_crop_calls == 2
assert [chunk.order for chunk in result.chunks] == sorted(chunk.order for chunk in result.chunks)
```

Add an expired-deadline test whose Luna draft contains readable text and whose adapter fails if Terra is called:

```python
assert result.markdown == "Deadline-safe content"
assert result.chunks[0].text == "Deadline-safe content"
assert "deadline_fallback_used" in result.chunks[0].warnings
```

Finally, retain an Audit regression assertion that figure reconciliation and precision crop calls still occur.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_page_processor.py -q
```

Expected: FAIL because crop checks remain serial and deadline fallback is absent.

- [ ] **Step 3: Extract existing stages into callback methods**

Move existing logic without changing prompts or schemas into these private methods on
`V2PageProcessor`: async `_draft_page(PageContext) -> DraftStage`, async
`_reconcile_page(DraftStage, PageContext) -> ReconciledStage`, synchronous
`_plan_verifications(ReconciledStage, PageContext) -> list[VerificationJob]`, async
`_run_verification(VerificationJob, PageContext) -> VerificationResult`, and synchronous
`_finalize_page(ReconciledStage, list[VerificationResult], PageContext) -> PageResult`.

Keep `_verify_crop` unchanged. `process_page` constructs `PageContext`, binds these methods
in `PageWorkflowCallbacks`, and passes `policy.crop_concurrency` as the workflow's
`max_concurrency` argument.

The plan step must be mechanical: prompts, schemas, quality thresholds, usage aggregation, deduplication, and Markdown assembly retain their current behavior.

- [ ] **Step 4: Implement deadline-safe finalization**

When optional work is skipped, finalize the draft chunks through the existing grounding and normalization path. For non-exact chunks, retain candidate text/Markdown and append `deadline_fallback_used`; do not emit an empty warning placeholder. Audit never uses this branch.

Wrap only the required Luna draft call in the remaining deadline:

```python
remaining = (deadline_at - datetime.now(UTC)).total_seconds()
if mode == ProcessingMode.BALANCED and remaining > 0:
    async with asyncio.timeout(remaining):
        draft = await callbacks.draft()
```

If the Luna call itself times out, construct a deterministic page draft from `page.native_words` in top/left order. If no native words exist, return one unresolved text chunk with `deadline_fallback_used`; this makes the provider failure explicit without blocking assembly.

- [ ] **Step 5: Run processor and worker regressions**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_page_workflow.py backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py -q
uv run ruff check backend/app/services/parsing/v2_page_workflow.py backend/app/services/parsing/v2_pipeline.py backend/app/services/parsing/v2_contracts.py backend/app/services/v2_worker.py backend/tests/unit/test_v2_page_workflow.py backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py
```

Expected: PASS.

- [ ] **Step 6: Commit workflow integration**

```powershell
git add backend/app/services/parsing/v2_pipeline.py backend/app/services/parsing/v2_contracts.py backend/tests/unit/test_v2_page_processor.py
git diff --staged
git commit -m "perf: parallelize balanced page verification"
```

---

### Task 4: Latency and Model-Call Observability

**Files:**
- Modify: `backend/app/services/parsing/v2_pipeline.py`
- Modify: `backend/app/services/v2_worker.py`
- Test: `backend/tests/unit/test_v2_page_processor.py`
- Test: `backend/tests/unit/test_v2_worker.py`

**Interfaces:**
- Produces structured log event `v2_page_processing_complete`.
- Produces structured fields `mode`, `page_number`, `prompt_version`, `latency_ms`, `model_calls`, `input_tokens`, `output_tokens`, `reconciliation_count`, `crop_count`, `cache_hit`, and `deadline_fallback`.

- [ ] **Step 1: Write failing log tests**

Use `caplog` or the project’s structured logger test pattern to assert the completion event is emitted once for a processed page and contains numeric latency/call counts. Assert no extracted phrase from the fake document appears in the serialized log record.

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py -q
```

Expected: FAIL because the completion event does not yet exist.

- [ ] **Step 3: Add one boundary log**

Measure with `time.perf_counter()` at `process_page` entry and emit one event after finalization:

```python
logger.info(
    "v2_page_processing_complete",
    mode=mode.value,
    page_number=page.page_number,
    prompt_version="v8",
    latency_ms=round((time.perf_counter() - started) * 1000, 1),
    model_calls=model_calls,
    input_tokens=result.input_tokens,
    output_tokens=result.output_tokens,
    reconciliation_count=reconciliation_count,
    crop_count=crop_count,
    deadline_fallback=deadline_fallback,
)
```

Log cache hits at the worker boundary with the same page and mode identifiers. Do not log prompts, chunk text, Markdown, filenames, source bytes, or API values.

- [ ] **Step 4: Run tests and lint**

Run:

```powershell
uv run pytest backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py -q
uv run ruff check backend/app/services/parsing/v2_pipeline.py backend/app/services/v2_worker.py backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py
```

Expected: PASS.

- [ ] **Step 5: Commit observability**

```powershell
git add backend/app/services/parsing/v2_pipeline.py backend/app/services/v2_worker.py backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py
git diff --staged
git commit -m "obs: record page extraction latency"
```

---

### Task 5: Balanced Cold-Cache Benchmark and Regression Gate

**Files:**
- Modify: `backend/scripts/benchmark_v2_accuracy.py:1-118`
- Create: `backend/tests/unit/test_benchmark_v2_accuracy.py`
- Modify: `README.md` processing-mode and verification sections

**Interfaces:**
- Produces CLI options `--mode {economy,balanced,audit}` and `--max-seconds FLOAT`.
- Produces report fields `elapsed_seconds`, `latency_gate_seconds`, and `latency_passed`.
- Retains LandingAI as ground truth and LlamaParse as peer comparison.

- [ ] **Step 1: Write failing CLI/report tests**

Test argument parsing and a mocked two-page run:

```python
assert args.mode == "balanced"
assert args.max_seconds == 180.0
assert report["mode"] == "balanced"
assert report["elapsed_seconds"] >= 0
assert report["latency_gate_seconds"] == 180.0
assert report["latency_passed"] is True
```

Patch `time.perf_counter` to test the failing path at 180.01 seconds.

- [ ] **Step 2: Run benchmark unit test and verify failure**

Run:

```powershell
uv run pytest backend/tests/unit/test_benchmark_v2_accuracy.py -q
```

Expected: FAIL because benchmark mode and timing fields are hardcoded or absent.

- [ ] **Step 3: Implement selectable mode and timing**

Replace `mode = ProcessingMode.AUDIT` with `ProcessingMode(args.mode)`. Measure from immediately before rendering/processing through page collection and Markdown assembly. Add:

```python
parser.add_argument("--mode", choices=[mode.value for mode in ProcessingMode], default="balanced")
parser.add_argument("--max-seconds", type=float, default=180.0)
```

Set `passed` to the existing accuracy gates for Audit, and to accuracy-reporting plus the latency gate for Balanced. Do not claim the existing 95% strict accuracy gate for Balanced unless the measured result reaches it.

- [ ] **Step 4: Update the README contract**

Document that Balanced targets 180 seconds for 10 cold-cache pages under normal provider availability, may skip optional verification near the deadline, and preserves candidate/native content. State that Audit has no 180-second target.

- [ ] **Step 5: Run all automated checks**

Run:

```powershell
uv run pytest backend/tests/unit -q
uv run ruff format --check backend/app backend/tests backend/scripts
uv run ruff check backend/app backend/tests backend/scripts
uv run pyright backend/app
git diff --check
```

Expected: tests and Ruff PASS. Record any pre-existing Pyright findings separately; fix only new findings introduced by this plan.

- [ ] **Step 6: Run the live 8-page accuracy comparison**

Remove only the benchmark output directory, not application caches outside that directory, then run:

```powershell
uv run python backend/scripts/benchmark_v2_accuracy.py `
  --mode balanced `
  --max-seconds 180 `
  --source "C:\Users\ahmad\OneDrive\Desktop\PublicWaterMassMailing.pdf" `
  --ground-truth "J:\New folder\landingai_output.md" `
  --peer "J:\New folder\llamaparse_output.md" `
  --candidate-markdown "D:\AI\.tmp\ade-balanced-benchmark\matched.md" `
  --report-json "D:\AI\.tmp\ade-balanced-benchmark\matched.json"
```

Record wall time, strict accuracy, token F1, model calls, and token usage. Compare against the current recorded reference rather than asserting an unmeasured improvement.

- [ ] **Step 7: Run the 10-page latency gate**

Use PyMuPDF in a temporary command to create `D:\AI\.tmp\ade-balanced-benchmark\ten-pages.pdf` by copying all eight source pages and repeating pages 1-2. This is a timing fixture only and must not be committed. Run the same Balanced benchmark against it with a matching temporary 10-page reference assembled from the LandingAI page sections.

Pass criteria:

```text
elapsed_seconds <= 180.0
document.md produced and non-empty
document.json produced by the application integration path and non-empty
no page loses all readable/native content because of deadline fallback
```

If the provider is rate-limited or unavailable, report the run as inconclusive rather than weakening the gate.

- [ ] **Step 8: Commit benchmark and documentation**

```powershell
git add backend/scripts/benchmark_v2_accuracy.py backend/tests/unit/test_benchmark_v2_accuracy.py README.md
git diff --staged
git commit -m "test: gate balanced PDF processing latency"
```

---

### Task 6: Final Diff and Risk Review

**Files:**
- Review only: all files changed by Tasks 1-5

**Interfaces:**
- Confirms no public artifact or API schema beyond documented timing metadata changed.

- [ ] **Step 1: Inspect the complete change set**

Run:

```powershell
git status --short
git diff HEAD~5 -- backend/app/config.py backend/app/services/parsing/v2_page_workflow.py backend/app/services/parsing/v2_pipeline.py backend/app/services/parsing/v2_contracts.py backend/app/services/v2_worker.py backend/scripts/benchmark_v2_accuracy.py backend/tests/unit README.md
```

Verify no unrelated dirty files were staged or changed by the implementation.

- [ ] **Step 2: Check the affected execution flow**

Use CodeGraph before manual search:

```powershell
codegraph explore "V2PageProcessor process_page run_page_workflow V2PageTaskRunner callers tests and affected flows"
```

Confirm the API queue, benchmark, and worker callers pass compatible arguments and that Audit retains its existing route.

- [ ] **Step 3: Re-run the narrow release gate**

```powershell
uv run pytest backend/tests/unit/test_v2_page_workflow.py backend/tests/unit/test_v2_page_processor.py backend/tests/unit/test_v2_worker.py backend/tests/unit/test_benchmark_v2_accuracy.py -q
uv run ruff check backend/app/services/parsing/v2_page_workflow.py backend/app/services/parsing/v2_pipeline.py backend/app/services/v2_worker.py backend/scripts/benchmark_v2_accuracy.py
git diff --check
```

Expected: PASS.

- [ ] **Step 4: Report measured outcome**

Handoff must state the measured 8-page and 10-page wall times, LandingAI strict accuracy and token F1, LlamaParse peer metrics, test commands, any pre-existing type-check findings, and whether the 180-second gate passed. Do not describe the SLA as guaranteed beyond normal provider availability.
