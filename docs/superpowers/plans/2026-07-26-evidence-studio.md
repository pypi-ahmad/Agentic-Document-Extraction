# Evidence Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Paperplane landing dashboard with the approved Graphite Signal document-first Evidence Studio.

**Architecture:** Keep API calls and workflow state in the home page while extracting run history, document rendering, and artifact preview into focused V2 components. Use browser object URLs for session-local uploads, existing artifact URLs for completed output, and CSS-only responsive behavior.

**Tech Stack:** Next.js 16, React 18, TypeScript, CSS custom properties, Lucide React, Vitest, Testing Library, Playwright CLI

## Global Constraints

- Do not add dependencies, backend endpoints, database changes, or new environment settings.
- Dark remains the default; the existing `paperplane:theme:v1` preference contract remains unchanged.
- Use Graphite Signal: charcoal surfaces, violet interaction accents, and semantic green/amber/red status colors.
- Historical source preview is limited to existing annotated PDF artifacts.
- Preserve all current V2 submission, polling, cancellation, artifact download, and evaluation behavior.
- Keep `main` as the only branch/worktree and perform one final normal push after all checks pass.

---

### Task 1: Lock the workspace contract with failing tests

**Files:**
- Modify: `frontend/src/app/page.test.tsx`

**Interfaces:**
- Consumes: existing mocked V2 API methods and `V2Job` fixture.
- Produces: public expectations for Configure, Results, Evaluate, run selection, local preview, and artifact preview behavior.

- [ ] **Step 1: Add a browser URL mock and richer job artifacts**

Add `URL.createObjectURL` and `URL.revokeObjectURL` spies in the test setup. Extend the fixture with Markdown, JSON, and annotated PDF artifacts so tests use the public artifact contract.

- [ ] **Step 2: Add focused failing tests**

Add tests that assert:

```tsx
expect(screen.getByRole("tab", { name: "Configure" })).toHaveAttribute("aria-selected", "true");
expect(screen.getByRole("navigation", { name: "Extraction runs" })).toBeInTheDocument();
expect(screen.getByLabelText("Choose document")).toBeInTheDocument();
```

After staging a PDF, assert that `createObjectURL` is called and the named document preview appears. For a completed job, assert Results is selected, Markdown/JSON artifact controls appear, fetched JSON is formatted, and preview failure leaves a download link visible. Retain the existing submission, cancellation, evaluation, model, and theme assertions.

- [ ] **Step 3: Verify RED**

Run:

```powershell
cd frontend
npm test -- --run src/app/page.test.tsx
```

Expected: FAIL because the Evidence Studio tabs, run navigation, and preview components do not exist.

### Task 2: Build focused preview and history components

**Files:**
- Create: `frontend/src/components/v2/RunHistory.tsx`
- Create: `frontend/src/components/v2/DocumentCanvas.tsx`
- Create: `frontend/src/components/v2/ArtifactPreview.tsx`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- `RunHistory({ jobs, activeId, onSelect })` renders the accessible run navigation.
- `DocumentCanvas({ source, status, errorMessage })` accepts `{ url, mimeType, label, remote } | null` and renders PDF, image, loading, unavailable, or failed states.
- `ArtifactPreview({ artifact, onSelect, artifacts })` previews text/JSON and always exposes downloads.

- [ ] **Step 1: Implement `RunHistory`**

Move run title, page progress, status formatting, and selection markup out of the page. Mark the active run with `aria-current="true"`.

- [ ] **Step 2: Implement `DocumentCanvas`**

Render local URLs directly. For remote PDF/image artifacts, fetch to a Blob URL, abort stale requests, revoke the generated URL during cleanup, and show an actionable fallback if loading fails.

- [ ] **Step 3: Implement `ArtifactPreview`**

Fetch text and JSON artifacts with `AbortController`, format valid JSON with two-space indentation, retain invalid JSON as text, and show loading/error/download-only states without hiding the download action.

- [ ] **Step 4: Recompose the page**

Keep job data, polling, upload settings, cancellation, evaluation, and theme state in `HomePage`. Add `WorkspaceTab = "configure" | "results" | "evaluate"`, preserve the newest local preview across successful submission, select Results for active runs, and render the three components inside the new shell.

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
cd frontend
npm test -- --run src/app/page.test.tsx
```

Expected: all page tests PASS without warnings.

- [ ] **Step 6: Commit behavior and tests**

```powershell
git add -- frontend/src/app/page.tsx frontend/src/app/page.test.tsx frontend/src/components/v2
git diff --cached --check
git diff --cached
git commit -m "feat: add document-first extraction workspace"
```

### Task 3: Apply Graphite Signal and responsive layout

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/v2-tools.css`

**Interfaces:**
- Consumes: the Evidence Studio class names and existing root `data-theme` value.
- Produces: complete dark/light tokens and responsive desktop, tablet, and mobile layouts.

- [ ] **Step 1: Replace the editorial layout tokens**

Define graphite surfaces, violet selection/action tokens, semantic status tokens, viewer canvas colors, focus-ring colors, and corresponding light values. Remove the page grid and oversized hero treatment.

- [ ] **Step 2: Style the four-region studio**

Use a full-height grid for the header, tool rail, run history, document canvas, and workspace panel. Keep headers and action bars sticky inside their panes and ensure independent scrolling.

- [ ] **Step 3: Add responsive collapse rules**

Below tablet width, hide the decorative rail and turn run history into a horizontal strip. Below mobile width, stack the document canvas above the workspace panel and preserve a minimum usable preview height.

- [ ] **Step 4: Run frontend checks**

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm test -- --run
npm run build
```

Expected: every command exits 0.

- [ ] **Step 5: Commit styling**

```powershell
git add -- frontend/src/app/globals.css frontend/src/app/v2-tools.css
git diff --cached --check
git diff --cached
git commit -m "style: apply Graphite Signal workspace theme"
```

### Task 4: Review, browser verification, and final push

**Files:**
- Review all changes since `origin/main`.

**Interfaces:**
- Produces: a verified `main` branch matching the approved design and ready on `origin/main`.

- [ ] **Step 1: Run backend and repository checks**

```powershell
uv run --locked pytest -q
uv run --locked ruff check .
uv run --locked pyright
```

- [ ] **Step 2: Browser-check real layouts with Playwright CLI**

Use the running development app or `scripts/dev.ps1`. Snapshot before interactions. Verify desktop dark/light, reload persistence, mobile collapse, empty and populated run states, artifact tabs, download fallbacks, and accessible names. Store screenshots only under ignored `output/playwright/`.

- [ ] **Step 3: Review structural impact and staged content**

Run CodeGraph change detection and affected-flow analysis, then:

```powershell
git diff --check
git status --short --branch
git log --oneline origin/main..HEAD
```

Scan changed files for bearer tokens and secret-key patterns without printing values.

- [ ] **Step 4: Push once and verify**

```powershell
git push origin main
git fetch origin
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Expected: the two SHAs match and the worktree is clean.

