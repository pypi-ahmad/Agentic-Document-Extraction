---
type: Testing
title: Tests, CI, and benchmark validation
description: The checked-in regression tests, continuous-integration gates, and the limits of benchmark corpus validation.
tags: [testing, ci, benchmark, validation]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-ab6fe8f88bea219f7d6fa86d
    resource: repo://benchmarks/manifest.json
  - id: openwiki-source-af5b2fc4a0830cd3de40e530
    resource: repo://benchmarks/README.md
  - id: openwiki-source-61e69b5756614e104fb07140
    resource: repo://scripts/benchmark_report.py
  - id: openwiki-source-bf4290575943b5a279a1aa5d
    resource: repo://tests/test_model_migration.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Tests, CI, and benchmark validation

The checked-in tests focus on request, billing, parsing fallback, and Streamlit UI regressions from the GPT-6 Sol migration. CI runs those tests alongside static checks, generated-document drift checks, benchmark corpus validation, and a Streamlit startup smoke test.

## Regression test coverage

The current test suite is in `tests/test_model_migration.py`. It uses an `httpx.MockTransport` for provider requests and Streamlit's `AppTest` for page checks. Covered behaviors include:

- OpenAI request fields, usage accounting, content-filter retries, and malformed response handling.
- Fallback to native PDF text or local OCR after a content-filter interruption.
- Replacing overgenerated page output with locally grounded text and avoiding duplicated grounded table-cell text.
- xAI reasoning and prompt-cache behavior, Markdown prompt files, cost calculations, the Cost page, and the default cloud model selector.

These tests exercise mocked requests and selected UI paths. They do not establish successful calls to a live provider or document-wide quality across every engine.

## Continuous integration

The GitHub Actions workflow runs on pushes and pull requests targeting `main`, and can also be started manually. Its Ubuntu job checks the Linux launcher syntax, installs the locked CPU/test/lint/docs environment, runs Ruff lint and format checks, Pyright, and `pytest -q`, then rebuilds generated documentation and checks for drift. It also validates the benchmark corpus and starts Streamlit on localhost, polling its health endpoint for up to 30 seconds.

## Benchmark corpus and report

`benchmarks/manifest.json` currently pins one attributed, MIT-licensed sample PDF by SHA-256. It lists the engines and metrics intended for evaluation. The manifest check in CI verifies that the pinned input is present with its expected hash; it does not run those engines or calculate the listed quality metrics.

`scripts/benchmark_report.py` validates the manifest and input hash, then writes a transparency page under `benchmark-site/`. If `benchmarks/results/latest.json` exists, the page displays it; otherwise, it reports that no measured result bundle is published. The benchmark README says the current corpus is too small for an accuracy claim and requires raw outputs, prompts, engine and model versions, timings, token counts, pricing, calibration-corpus hash, and failures for publishable results.

## Related pages

- [Paperplane system overview](../architecture/system-overview.md)
- [Contracts and exported formats](../concepts/contracts-and-exports.md)
- [Parse workflow and grounded assembly](../workflows/parse-document.md)
