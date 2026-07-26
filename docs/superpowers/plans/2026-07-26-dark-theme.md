# Dark Theme Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Paperplane dark by default and add an accessible, persisted light/dark toggle.

**Architecture:** Keep theme ownership in the existing client home page. The layout continues to set the pre-hydration theme, the page synchronizes and persists user changes, and semantic CSS variables provide both palettes without a dependency or layout change.

**Tech Stack:** Next.js 16, React 18, TypeScript, CSS custom properties, Lucide React, Vitest, Testing Library

## Global Constraints

- Dark is the initial theme when no valid saved preference exists.
- Persist explicit choices under `paperplane:theme:v1`.
- Do not add system-preference detection, a third-party theme dependency, or additional themes.
- Preserve the existing layout, typography, responsive behavior, and green/amber/red identity.
- Storage failures must not prevent in-page theme switching.
- Do not stage or commit pre-existing unrelated working-tree changes.

---

## File Structure

- Modify `frontend/src/app/page.tsx`: own theme state, storage synchronization, toggle behavior, and masthead control.
- Modify `frontend/src/app/page.test.tsx`: verify the public toggle contract, persistence, and storage-failure fallback.
- Modify `frontend/src/app/globals.css`: define semantic light/dark tokens and style all primary surfaces and the toggle.
- Modify `frontend/src/app/v2-tools.css`: consume the same semantic tokens in secondary controls, preview, and evaluation UI.

### Task 1: Accessible persisted theme toggle

**Files:**
- Modify: `frontend/src/app/page.test.tsx`
- Modify: `frontend/src/app/page.tsx`

**Interfaces:**
- Consumes: the layout's root `data-theme` value and `localStorage["paperplane:theme:v1"]`.
- Produces: a masthead button named `Switch to light theme` or `Switch to dark theme`; root `data-theme: "dark" | "light"`; persisted theme value when storage is available.

- [ ] **Step 1: Reset theme state in the existing test setup and add failing public-contract tests**

Add `document.documentElement.dataset.theme = "dark"` and `localStorage.clear()` to `beforeEach`. Add these tests inside the existing describe block:

```tsx
it("switches themes and persists the explicit preference", async () => {
  render(<HomePage />);

  const toLight = screen.getByRole("button", { name: "Switch to light theme" });
  fireEvent.click(toLight);

  expect(document.documentElement).toHaveAttribute("data-theme", "light");
  expect(localStorage.getItem("paperplane:theme:v1")).toBe("light");

  fireEvent.click(screen.getByRole("button", { name: "Switch to dark theme" }));

  expect(document.documentElement).toHaveAttribute("data-theme", "dark");
  expect(localStorage.getItem("paperplane:theme:v1")).toBe("dark");
});

it("still switches theme when preference storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => {
    throw new DOMException("Storage unavailable");
  });
  render(<HomePage />);

  fireEvent.click(screen.getByRole("button", { name: "Switch to light theme" }));

  expect(document.documentElement).toHaveAttribute("data-theme", "light");
  expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused tests and verify the new contract fails**

Run:

```powershell
cd frontend
npm test -- --run src/app/page.test.tsx
```

Expected: FAIL because the theme toggle does not exist.

- [ ] **Step 3: Implement the minimal theme state and toggle**

In `page.tsx`, import `Moon` and `Sun`, define the storage key, and add the state alongside the existing page state:

```tsx
const THEME_STORAGE_KEY = "paperplane:theme:v1";
type Theme = "light" | "dark";

const [theme, setTheme] = useState<Theme>("dark");

useEffect(() => {
  const initial = document.documentElement.dataset.theme;
  setTheme(initial === "light" ? "light" : "dark");
}, []);

function toggleTheme() {
  const next: Theme = theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  setTheme(next);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    // The selected theme still applies for this page when storage is blocked.
  }
}
```

Place the control at the end of the masthead, grouping it with the existing model chain:

```tsx
<div className="masthead-actions">
  <div className="model-chain">...</div>
  <button
    className="theme-toggle"
    type="button"
    aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
    onClick={toggleTheme}
  >
    {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
  </button>
</div>
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```powershell
cd frontend
npm test -- --run src/app/page.test.tsx
```

Expected: all `page.test.tsx` tests PASS.

- [ ] **Step 5: Commit only the toggle and its tests**

```powershell
git add -- frontend/src/app/page.tsx frontend/src/app/page.test.tsx
git diff --staged --check
git diff --staged
git commit -m "feat: add persisted theme toggle"
```

### Task 2: Theme-aware visual tokens

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/app/v2-tools.css`

**Interfaces:**
- Consumes: `document.documentElement.dataset.theme` values `light` and `dark` from Task 1.
- Produces: semantic tokens used by every existing surface: `--paper`, `--panel`, `--panel-muted`, `--control`, `--line`, `--ink`, `--muted`, `--grid`, `--shadow`, `--green`, `--green-soft`, `--amber`, `--red`, `--error-bg`, `--error-line`, `--drop-line`, `--progress`, `--stop-bg`, `--stop-line`, and `--preview-bg`.

- [ ] **Step 1: Define complete light and dark palettes**

Replace the current root token declaration at the start of `globals.css` with semantic values:

```css
:root {
  --ink: #17211b;
  --muted: #647269;
  --paper: #f4f0e7;
  --panel: #fffdf8;
  --panel-muted: #f7f5ee;
  --control: #ffffff;
  --line: #d9d4c9;
  --grid: #31493b09;
  --shadow: #24372b0a;
  --green: #195f43;
  --green-soft: #e4efe8;
  --amber: #b76524;
  --red: #a33b32;
  --error-bg: #f9e9e7;
  --error-line: #e2b4ae;
  --drop-line: #9baa9f;
  --progress: #e4e1d8;
  --stop-bg: #fbefed;
  --stop-line: #dfb2ad;
  --preview-bg: #eeeeee;
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --ink: #edf5ef;
  --muted: #9eafa4;
  --paper: #0b100d;
  --panel: #111914;
  --panel-muted: #0e1611;
  --control: #152019;
  --line: #29382f;
  --grid: #8eb69b0d;
  --shadow: #00000052;
  --green: #63c994;
  --green-soft: #173526;
  --amber: #e2a15e;
  --red: #f08c82;
  --error-bg: #351b1b;
  --error-line: #70403c;
  --drop-line: #52675a;
  --progress: #26342b;
  --stop-bg: #321c1b;
  --stop-line: #68403c;
  --preview-bg: #0a0d0b;
}
```

- [ ] **Step 2: Replace hardcoded component colors with the semantic tokens**

In `globals.css`, make these exact substitutions while leaving sizing and layout unchanged:

```css
body { background-image: linear-gradient(var(--grid) 1px, transparent 1px), linear-gradient(90deg, var(--grid) 1px, transparent 1px); }
.masthead { background: color-mix(in srgb, var(--panel) 91%, transparent); }
.error { border-color: var(--error-line); background: var(--error-bg); }
.setup, .runs { box-shadow: 0 10px 30px var(--shadow); }
.field select, .artifact { background: var(--control); }
.dropzone, .job-list { background: var(--panel-muted); }
.dropzone { border-color: var(--drop-line); }
.job-list button.active { background: var(--control); }
.progress { background: var(--progress); }
.stop { border-color: var(--stop-line); background: var(--stop-bg); }
```

Add toggle layout and interaction rules:

```css
.masthead-actions { display: flex; align-items: center; gap: 10px; }
.theme-toggle {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: var(--panel);
  color: var(--ink);
  cursor: pointer;
}
.theme-toggle:hover { border-color: var(--green); color: var(--green); }
```

In `v2-tools.css`, replace `background: white` with `background: var(--control)` and `background: #eee` with `background: var(--preview-bg)`.

- [ ] **Step 3: Run the complete frontend verification suite**

Run:

```powershell
cd frontend
npx tsc --noEmit
npm run lint
npm test -- --run
npm run build
```

Expected: each command exits 0; all component tests pass; Next.js produces a successful production build.

- [ ] **Step 4: Perform the visual acceptance check**

Run the application from the repository root:

```powershell
.\scripts\dev.ps1
```

Open the printed frontend URL. Confirm both themes render legibly at desktop and a viewport below 680 px, including the masthead, form controls, dropzone, empty/job states, metrics, artifact links, errors, and PDF preview. Reload after selecting light, then dark, and confirm each choice persists without a flash of the other theme.

- [ ] **Step 5: Review and commit only the visual token changes**

```powershell
git add -- frontend/src/app/globals.css frontend/src/app/v2-tools.css
git diff --staged --check
git diff --staged
git commit -m "style: add dark and light theme palettes"
```

### Task 3: Final change review

**Files:**
- Review: `frontend/src/app/page.tsx`
- Review: `frontend/src/app/page.test.tsx`
- Review: `frontend/src/app/globals.css`
- Review: `frontend/src/app/v2-tools.css`

**Interfaces:**
- Consumes: completed theme behavior and palettes from Tasks 1 and 2.
- Produces: verified implementation ready for user handoff without modifying unrelated files.

- [ ] **Step 1: Inspect the final scoped diff and working tree**

```powershell
git status --short
git diff HEAD~2 -- frontend/src/app/page.tsx frontend/src/app/page.test.tsx frontend/src/app/globals.css frontend/src/app/v2-tools.css
```

Expected: only the approved toggle, tests, and theme styling appear in the scoped diff; pre-existing unrelated dirty files remain uncommitted.

- [ ] **Step 2: Scan the scoped diff for secrets and environment-specific values**

```powershell
git diff HEAD~2 -- frontend/src/app/page.tsx frontend/src/app/page.test.tsx frontend/src/app/globals.css frontend/src/app/v2-tools.css | Select-String -Pattern 'OPENAI_API_KEY|Bearer\s+|sk-[A-Za-z0-9]+'
```

Expected: no matches.

- [ ] **Step 3: Record final verification for handoff**

Report the four modified frontend paths, the successful TypeScript/lint/test/build commands, the visual check result, unchanged pre-existing working-tree modifications, and any residual browser-specific risk.
