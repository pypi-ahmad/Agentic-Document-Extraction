# Changelog

All notable changes to this project will be documented in this file.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

### Changed

### Fixed

## [0.2.0] - 2026-06-22

### Added

- **GLM-OCR parser engine.** New `glmocr` parser runs the GLM-OCR
  vision-language OCR model against a local Ollama server
  (default `http://localhost:11434`, model `glm-ocr:latest`).
  Enable with `ENABLE_GLM_OCR=true`; supports PNG, JPEG, TIFF.
  Includes a text-cleanup pass that strips GLM-OCR's
  HTML/markdown scaffolding and deduplicates repeated
  transcriptions.
- **uv-managed project.** Top-level `pyproject.toml` and
  `.python-version` (3.12.10) with optional extras for `paddleocr`,
  `ollama`, `test`, and `lint`. Run `uv venv --python 3.12.10 .venv`
  then `uv pip install -e ".[test,lint,ollama]"`. `uv.lock` is
  committed for reproducible installs.
- **Zero-to-hero docs.** New `docs/ARCHITECTURE.md`,
  `docs/DEVELOPMENT.md`, `docs/GLM_OCR.md`, and
  `docs/LIMITATIONS.md`.
- **13 new unit tests** for the GLM-OCR provider in
  `backend/tests/test_glm_ocr_provider.py`.

### Changed

- README rewritten as a professional, zero-to-hero guide.
- `backend/app/main.py` — `app.version` bumped to `0.2.0`.
- `backend/app/models/enums.py` — `ParserEngine` now includes
  `GLMOCR = "glmocr"`.
- `backend/app/services/ocr/registry.py` — `AUTO_PRIORITY` now
  starts with GLM-OCR before PaddleOCR; `_import_builtin_providers`
  registers the new engine.
- `backend/app/models/schemas.py` — `OCREngineFlags` exposes a
  `glm_ocr: bool` field.
- `backend/app/routers/providers.py` — `/api/providers/config`
  returns the new `glm_ocr` flag.
- `backend/.env.example` — documents the new env vars
  (`ENABLE_GLM_OCR`, `OLLAMA_BASE_URL`, `OLLAMA_GLM_OCR_MODEL`,
  `GLM_OCR_TIMEOUT_SECONDS`).
- `frontend/src/lib/api.ts` — `ParserEngine` mirror enum and
  display-name map include `glmocr`.
- `pyproject.toml` (root) — consolidated project metadata, deps,
  pytest, and ruff configuration.

### Fixed

- The OCR registry test
  (`test_list_provider_statuses_excludes_internal_fallback_by_default`)
  was hard-coded to expect only `paddleocr`; updated to include
  `glmocr` in the user-selectable list.

## [2026-06-13]

### Added

- OSS companion documentation initialized (license, contributing, security, conduct, changelog).
