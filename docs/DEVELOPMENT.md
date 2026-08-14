# Development

## Environment

```powershell
uv python install 3.12.10
uv sync --locked --extra test --extra lint --extra docs
uv run streamlit run streamlit_app.py
```

`Paperplane.cmd` is the end-user entry point. It installs runtime dependencies and Docling
models; development extras remain an explicit developer installation.

Configuration precedence is existing process/user environment, ignored `.env`, ignored
Streamlit secrets, then the default OpenAI base URL. Keep only safe placeholders in
`.env.example` and `.streamlit/secrets.toml.example`.

## Important paths

- `streamlit_app.py` — complete user interface and session state
- `paperplane/runtime.py` — parser composition and client lifetime
- `paperplane/ingest.py` — validation, PDF classification, and rendering
- `paperplane/parser.py` — automatic document routing and assembly
- `paperplane/docling_parser.py` — local native-document conversion
- `paperplane/pipeline.py` — vision drafting and bounded verification
- `paperplane/grounding.py` — coordinate transforms and text alignment
- `paperplane/contracts.py` — grounded output contract
- `paperplane/annotated_pdf.py` — evidence artifacts
- `tests/` — parser, contract, routing, artifact, and Streamlit AppTest coverage

## Change rules

- Work on `main` and preserve unrelated local edits.
- Keep parsing logic independent from Streamlit widgets.
- Validate all untrusted input at the parser boundary.
- Do not cache uploads, model responses, annotated PDFs, results, or credentials.
- Caching the Docling converter is allowed because it retains model resources only.
- Sanitize model-produced HTML before rendering it.
- Do not add a database, API server, queue, frontend framework, or persistence layer for
  session-local behavior.
- Update affected documentation with every observable code change.
- Keep `.codegraph/`, `.code-review-graph/`, `.ua/`, and `graphify-out/` available for
  versioning; ignore only their transient runtime/cache files.

Use the repository knowledge graph before broad searches when available. If it is
unavailable or stale, state that and fall back to targeted `rg` and focused file reads.

## Verification

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

For UI changes, run the app and inspect upload, preview, parse, all four result tabs, and all
three downloads. Rebuild generated documentation after source changes:

```powershell
uv run python scripts/build_handbook.py
uv run python scripts/build_app_guide.py
```
