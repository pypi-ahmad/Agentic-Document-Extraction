# Release process

> How a change becomes a numbered, tagged, published GitHub release.

This is the canonical, scripted workflow. **Do it the manual way for
small fixes; use the script for anything user-facing.**

---

## 1. Versioning rules

The project follows [Semantic Versioning](https://semver.org/):

| Bump    | When                                                              | Examples                         |
| ------- | ----------------------------------------------------------------- | -------------------------------- |
| `major` | Breaking change to a public API, schema, or persistence shape.    | `0.x → 1.0.0`                    |
| `minor` | New feature, additive change, new engine, new endpoint.           | `0.2.0 → 0.3.0`                  |
| `patch` | Bug fix, doc fix, internal refactor with no behaviour change.     | `0.2.0 → 0.2.1`                  |

The version lives in three places and the release script keeps them
in sync:

- `pyproject.toml` — `[project] version`
- `backend/app/main.py` — `app = FastAPI(..., version=...)`
- `CHANGELOG.md` — `## [X.Y.Z] - YYYY-MM-DD`

The Python `__version__` constant is intentionally not used; the
`/info` endpoint reads `app.version` and that is the source of truth
exposed to the UI.

---

## 2. Branch and commit hygiene

- All work lands on `main` via PRs.
- Each PR runs the CI matrix (lint, format check, pytest on
  Python 3.12.10, frontend lint + build). CI must be green before
  merging.
- The release commit itself is created *after* the merge by the
  release script.

---

## 3. Cutting a release

### 3.1 Decide the bump

- Look at the merged PRs since the last release on
  <https://github.com/pypi-ahmad/Agentic-Document-Extraction/releases>.
- Apply the rules in §1.

### 3.2 Run the release script (recommended)

The script (`scripts/release.py`) does the whole thing — bump the
three version strings, rewrite the CHANGELOG, commit, tag, push, and
create the GitHub release.

```bash
# Local sanity check — shows the plan, touches nothing.
python scripts/release.py --dry-run --bump minor

# Cut the release.
python scripts/release.py --bump minor --push
```

Useful flags:

```text
--bump {major,minor,patch}    Semver component to bump.
--version X.Y.Z              Set the version explicitly.
--title "vX.Y.Z — title"     Release title (otherwise derived).
--notes "..."                Inline release notes.
--notes-file PATH            Release notes from a file (e.g. /tmp/notes.md).
--target BRANCH              Branch to tag (default: main).
--push                       Push branch + tag, create GH release.
--remote NAME                Git remote (default: origin).
--dry-run                    Print the plan, do not write.
```

If `--notes` is omitted, the script drafts release notes from the
conventional-commit subjects since the last tag. **Always review the
draft** before running with `--push`.

### 3.3 Publish Python package (TestPyPI + PyPI)

v0.6.0+ uses GitHub Actions + Trusted Publishing (OIDC).

Workflows:

- `.github/workflows/publish-testpypi.yml`
- `.github/workflows/publish-pypi.yml`

Trigger behavior:

- TestPyPI: manual `workflow_dispatch` or prerelease publish.
- PyPI: release `published` (non-prerelease) or manual `workflow_dispatch`.

Both workflows build with `uv build`, validate with `twine check`, then publish
with `pypa/gh-action-pypi-publish`.

#### One-time setup in package indexes

Create Trusted Publisher entries in both TestPyPI and PyPI for this repository.

- Owner: `pypi-ahmad`
- Repository: `Agentic-Document-Extraction`
- Workflow file:
  - TestPyPI: `.github/workflows/publish-testpypi.yml`
  - PyPI: `.github/workflows/publish-pypi.yml`
- Environment names:
  - TestPyPI: `testpypi`
  - PyPI: `pypi`

No API tokens needed when Trusted Publishing is configured correctly.

#### Verify published artifacts

```bash
# PyPI
pip install agentic-document-extraction

# TestPyPI
pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple \
  agentic-document-extraction
```

### 3.4 Manual flow (small fixes only)

If you really want to do it by hand:

```bash
# 1. Edit the three version strings.
$EDITOR pyproject.toml backend/app/main.py CHANGELOG.md

# 2. Commit.
git add pyproject.toml backend/app/main.py CHANGELOG.md
git commit -m "chore(release): 0.2.1"

# 3. Tag.
git tag -a v0.2.1 -m "v0.2.1 — <summary>"

# 4. Push.
git push origin main
git push origin v0.2.1

# 5. GitHub release.
gh release create v0.2.1 \
  --title "v0.2.1 — <summary>" \
  --notes-file /path/to/notes.md \
  --target main
```

---

## 4. After the release

1. **Verify** the GitHub release page renders the notes correctly:
   <https://github.com/pypi-ahmad/Agentic-Document-Extraction/releases/tag/vX.Y.Z>
2. **Confirm CI** still passes on `main` (the release commit itself
   is exercised by the matrix on push).
3. **Smoke-test** the published version locally:
   ```bash
   git checkout v0.2.1
   uv venv --python 3.12.10 .venv
   source .venv/bin/activate
   uv pip install -e ".[test,lint,ollama]"
   pytest backend/tests/ -q
   uvicorn app.main:app --port 8000 --app-dir backend
   curl -s localhost:8000/info | jq .version
   # → "0.2.1"
   ```
4. **Close the milestone** in GitHub Issues if the release resolves
   any tracked issues.

---

## 5. Pre-release builds

For `0.x.y` versions, GitHub treats them as regular releases (not
pre-releases). Use `--prerelease` only for explicit `alpha.N`,
`beta.N`, or `rc.N` tags:

```bash
python scripts/release.py \
  --version 0.3.0-beta.1 \
  --title "v0.3.0-beta.1 — first beta" \
  --push
```

The script does not yet support pre-release identifiers in the
auto-derive path; if you need one, set `--version` explicitly.

---

## 6. Hotfixes

For a critical patch to a shipped release:

```bash
# 1. Create a hotfix branch from the tag.
git checkout -b hotfix/v0.2.1 v0.2.0

# 2. Fix, commit, push, open PR, merge to main.

# 3. Run the script with --version explicitly.
python scripts/release.py --version 0.2.1 --push
```

The script refuses to release a version lower than the one in
`pyproject.toml`, so accidental downgrades fail loudly.

---

## 7. CI

`.github/workflows/ci.yml` runs on every push and PR to `main`:

- Ruff lint and format check on the new code
- Full `pytest` suite on Python 3.12.10
- Coverage report (xml artefact for downstream Codecov / Sonar)
- Frontend `npm run lint` and `npm run build`

See the workflow file for the exact matrix and the cached uv
dependencies.
