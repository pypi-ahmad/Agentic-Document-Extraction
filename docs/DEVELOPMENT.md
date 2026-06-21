# Development

> Everything you need to install, run, test, lint, and extend the
> project on a fresh checkout.

---

## 1. Environment

- **Python:** pinned to `3.12.10` (`.python-version`).
- **Node:** 18+ for the Next.js frontend.
- **Tooling:** [uv](https://docs.astral.sh/uv/) for Python
  dependencies and virtualenvs. `uv` reads `pyproject.toml` and
  `.python-version`; you do not need to manage `pip` or `python`
  versions by hand.

Install `uv` if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## 2. First-time setup

From the repository root:

```bash
# 1. Create the project venv at the exact pinned Python version.
uv venv --python 3.12.10 .venv

# 2. Activate it.
source .venv/bin/activate
#    (Windows: .venv\Scripts\activate)

# 3. Install the project, including test, lint, and Ollama extras.
uv pip install -e ".[test,lint,ollama]"

# 4. Optional extras:
uv pip install -e ".[paddleocr]"    # PaddleOCR + paddlepaddle
```

The editable install (`-e`) means source changes in `backend/app/`
take effect without reinstalling.

### Configuration

```bash
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum, set one LLM API key.
```

Common additions:

```bash
# Local GLM-OCR (vision-language OCR via Ollama)
echo "ENABLE_GLM_OCR=true" >> .env
ollama pull glm-ocr:latest
```

### Running the backend

```bash
uvicorn app.main:app --reload --port 8000 --app-dir backend
```

Interactive docs:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>

### Running the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:3000>.

---

## 3. Tests

```bash
# Full suite, no network
pytest backend/tests/ -q

# Verbose, fail-fast
pytest backend/tests/ -x -v

# One module
pytest backend/tests/test_glm_ocr_provider.py -v

# With coverage
pytest --cov=app --cov-report=term-missing backend/tests/
```

Test conventions:

- `asyncio_mode = "auto"` is set in `pyproject.toml`, so plain
  `async def test_…` functions are run automatically.
- Network is stubbed with `unittest.mock.patch` on `httpx` /
  provider clients; no test needs a real API key.
- Provider tests use `monkeypatch.setattr(settings, …)` to flip
  feature flags rather than touching env vars.

---

## 4. Lint and format

```bash
# Lint
ruff check backend/app backend/tests

# Auto-fix what's safe
ruff check --fix backend/app backend/tests

# Format
ruff format backend/app backend/tests
```

`ruff` is configured in `pyproject.toml` with sensible defaults:
line length 100, Python 3.12, `E`/`W`/`F`/`I`/`B`/`UP`/`C4`/`SIM`/`RUF`
enabled. The `B008` (FastAPI argument defaults) and `B904` (raise from
inside except) rules are disabled project-wide; tests are allowed to
be slightly looser.

---

## 5. Project layout

```
.
├── pyproject.toml          # Project metadata, deps, ruff, pytest
├── .python-version         # Pinned Python for uv
├── backend/
│   ├── app/                # FastAPI app package
│   ├── scripts/            # Live validation scripts
│   └── tests/              # pytest suite
├── frontend/               # Next.js 14 app
└── docs/                   # Zero-to-hero documentation
```

The Python package is `app` (under `backend/`). `pyproject.toml`
points the wheel builder at `backend/app`.

---

## 6. Adding a new OCR engine

1. Subclass `BaseOCRProvider` in
   `backend/app/services/ocr/your_engine_provider.py`.
2. Implement `provider_id`, `display_name`, and `extract_text`.
3. If the engine needs a feature flag, set the class attribute
   `feature_flag_name = "enable_your_engine"`.
4. If it only supports a subset of file types, set
   `supported_file_types = frozenset({...})`.
5. Append the class to `_PROVIDER_CLASSES` in
   `backend/app/services/ocr/registry.py::_import_builtin_providers`.
6. Add the engine id to `ParserEngine` (only if the user should pick
   it directly; internal helpers stay out of the enum).
7. Optionally insert it into `AUTO_PRIORITY` so `auto` can route to
   it.
8. Update `AppConfigResponse.ocr_engine_flags` if you added a
   feature flag and want the UI to show it.
9. Add a focused test under `backend/tests/test_<engine>_provider.py`.
10. Add a row to the docs' "Supported file types and parsers" table.

That's it — the rest of the system sees the new engine through
`get_ocr_provider("your_engine")` and the registry's status helpers.

---

## 7. Adding a new LLM provider

Same idea, different base:

1. Subclass `BaseLLMProvider` in
   `backend/app/services/llm/your_provider.py`.
2. Implement the abstract members (`provider_id`, `display_name`,
   `get_api_key`, `is_extraction_client_available`,
   `_list_models_dynamic`, `extract`).
3. Use `app/services/llm/output_parser.py::parse_llm_json` and
   `coerce_to_schema` to handle messy model output.
4. Add the class to `app/services/llm/registry.py::_import_builtin_providers`.
5. Add the provider id to `LLMProviderID`.
6. Add an API-key field to `app/config.py::Settings` (optional,
   empty default).
7. Insert into `AUTO_PRIORITY` if you want `auto` to consider it.
8. Add a test stub under `backend/tests/test_<provider>.py`.
9. Update the README and the UI's display-name map
   (`frontend/src/lib/api.ts::PROVIDER_DISPLAY_NAMES`).

---

## 8. Debugging tips

- **`/info`** returns runtime capabilities (Python version, parser
  counts, LLM counts, supported file types). Use it to confirm the
  backend sees the providers you think it does.
- **`/health?detail=true`** returns document/extraction counts, DB
  size, and disk usage for `uploads/` and `artifacts/`.
- **Set `DEBUG=true`** in `.env` to log every SQL statement from
  SQLAlchemy.
- The `error` and `error_category` fields on an `extraction` row
  tell you *what* failed; the `extraction_steps` rows tell you
  *when*. The two together usually pinpoint the issue in seconds.
- For SSE debugging, the browser dev tools' "EventStream" tab in
  the network panel shows the raw frames; `curl -N
  http://localhost:8000/api/extractions/<id>/stream` is the CLI
  equivalent.

---

## 9. CI suggestions

There is no CI configured in this repo, but a minimal GitHub Actions
workflow would be:

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          python-version: "3.12.10"
      - run: uv venv --python 3.12.10 .venv
      - run: uv pip install -e ".[test,lint]"
      - run: ruff check backend/app backend/tests
      - run: ruff format --check backend/app backend/tests
      - run: pytest backend/tests/ -q
```

---

## 10. Style and conventions

- **Type hints everywhere**, including return types.
- **Async by default** for any I/O.
- **Logging**, not `print`, for diagnostics.
- **Pydantic v2** for any new request/response models.
- **StrEnum** for any new wire-format string enums — values are
  the actual strings used in URLs and JSON.
- **Pydantic Settings**, not module-level `os.getenv`, for any new
  config flag.
- **Frozen dataclasses** for internal value objects.
- **No comments** unless something is genuinely non-obvious.
- **Ruff is the source of truth** for formatting; `ruff format` and
  CI should be a no-op on a clean tree.
