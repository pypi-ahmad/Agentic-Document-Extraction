# Contributing

> Thanks for helping improve Agentic Document Extraction.

## Where to start

1. Skim [`README.md`](README.md) for the user-facing overview.
2. Skim [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the system shape.
3. Skim [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) for the dev workflow.
4. Skim [`RELEASE.md`](RELEASE.md) for the release process (only relevant if you have write access).

## Ground rules

- **Open an issue first** for non-trivial changes. Use the issue templates in `.github/ISSUE_TEMPLATE/`.
- **One change per PR.** Easier to review, easier to revert.
- **Tests are required.** No PR is merged without a green test run.
- **Conventional Commits** for every commit (`feat:`, `refactor:`, `perf:`, `test:`, `docs:`, `chore:`, `fix:`).
- **No force-pushes.** Add fixup commits instead.
- **No direct pushes to `main`.** Open a PR, wait for CI, then merge.
- **Backward compatibility by default.** Breaking changes need an ADR in [`docs/adr/`](docs/adr/) and a Migration section in the release notes.

## Local setup

```bash
uv venv --python 3.12.10 .venv
source .venv/bin/activate
uv pip install -e ".[test,lint,ollama]"

# Optional: image OCR engine
uv pip install -e ".[paddleocr]"

# Optional: Redis-backed job queue
uv pip install -e ".[queue]"

# Optional: OpenTelemetry exporter
uv pip install -e ".[otel]"
```

## Before opening a PR

Run the full local check:

```bash
ruff check backend/app backend/tests scripts
ruff format --check backend/app backend/tests scripts
pyright backend/app scripts/release.py
pytest backend/tests/ -q
```

CI runs the same matrix on Node 22 and Python 3.12.10. A red CI means the PR is not mergeable.

## Adding a new provider

See [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) §6 (OCR) and §7 (LLM) for the step-by-step pattern. The summary is: subclass the base, register in the registry, add an enum value, add a feature flag, add tests, add a doc row.

## Security

If you find a vulnerability, **do not** open a public issue. Follow [`SECURITY.md`](SECURITY.md).

## Code of conduct

This project follows [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
