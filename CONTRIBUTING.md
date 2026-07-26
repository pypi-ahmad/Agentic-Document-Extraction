# Contributing

> Thanks for helping improve Agentic Document Extraction.

## Where to start

1. Read [`README.md`](README.md) for the product and runtime prerequisites.
2. Read [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the pipeline boundary.
3. Follow [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for setup, tests, and local runs.
4. Read [`RELEASE.md`](RELEASE.md) only when preparing a release.

## Ground rules

- **Open an issue first** for non-trivial changes. Use the issue templates in `.github/ISSUE_TEMPLATE/`.
- **One change per PR.** Easier to review, easier to revert.
- **Tests are required.** No PR is merged without a green test run.
- **Conventional Commits** for every commit (`feat:`, `refactor:`, `perf:`, `test:`, `docs:`, `chore:`, `fix:`).
- **No force-pushes.** Add fixup commits instead.
- **No direct pushes to `main`.** Open a PR, wait for CI, then merge. Release maintainers
  may create the final tagged release commit after merge.
- **Backward compatibility by default.** Breaking changes need an ADR in [`docs/adr/`](docs/adr/) and a Migration section in the release notes.

## Local setup

```powershell
uv python install 3.12.10
uv sync --locked
Set-Location frontend
npm ci
```

The official PaddleOCR-VL parser runs inside its pinned GPU Docker image. Do not add
PaddlePaddle to the host environment. See `docs/RUN_APP.md` for Docker, GPU, Ollama,
and persistent model-cache setup.

## Before opening a PR

Run the full local check:

```bash
uv run ruff check backend/app backend/tests scripts
uv run ruff format --check backend/app backend/tests scripts
uv run pytest backend/tests/unit -q
cd frontend && npm run lint && npm test && npm run build
```

CI runs the same matrix on Node 22 and Python 3.12.10. A red CI means the PR is not mergeable.

## Changing parsing behavior

Keep the Docker worker contract, parse-job API, and persisted job artifacts compatible
unless the change explicitly includes a migration. Add a focused unit or API test for
each behavior change and update the relevant architecture or runtime document.

## Security

If you find a vulnerability, **do not** open a public issue. Follow [`SECURITY.md`](SECURITY.md).

## Code of conduct

This project follows [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
