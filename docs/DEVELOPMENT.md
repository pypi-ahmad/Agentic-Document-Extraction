# Development

```powershell
uv python install 3.12.10
uv sync --locked --extra cpu --extra test --extra lint --extra docs
uv run --extra cpu streamlit run workspace_app.py --server.port=8551
```

Prepare or verify the local detector used by profiled Ollama OCR families:

```powershell
uv run --locked --extra cpu python -m paperplane.ollama_ocr --download
uv run --locked --extra cpu python -m paperplane.ollama_ocr --check
```

`workspace_app.py` defines Parse, Organize, Jobs, and Cost navigation;
`streamlit_app.py` remains the Parse page. Other pages are under `app_pages/`. Session
usage is attributed in the framework-neutral parse contracts before the Cost page
aggregates it. Core modules must not import Streamlit.

Run checks:

```powershell
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run ruff format --check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
uv run python scripts/benchmark_report.py
```

Use the internal `ParseResponse` as an engine assembly boundary. Public interchange goes
through `to_ade_v2_parse()` or `to_paperplane_export()`. Never invent ranges, boxes,
citations, confidence calibration, or benchmark scores. Add a matching profile/corpus hash
before describing a confidence value as calibrated.

After code changes, update README, active docs, changelog/release notes, and generated
guides. Rebuild them with `scripts/build_app_guide.py` and `scripts/build_handbook.py`.
