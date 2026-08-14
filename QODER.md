# Qoder instructions for Paperplane

## Product contract

Paperplane is a local Streamlit application that converts PDFs, images, and modern Office
documents into layout-aware Markdown, hierarchical grounding JSON, and an annotated PDF.
It is inspired by LandingAI ADE's observable document-output workflow, but it does not call
LandingAI ADE or claim compatibility with its private models or benchmarks.

The supported architecture is:

```text
streamlit_app.py -> paperplane.runtime -> AgenticDocumentParser
                  -> Docling for native content
                  -> OpenAI vision for scans and images
                  -> Markdown/grounding assembly -> annotated PDF
```

There is no database, REST API, background worker, JavaScript frontend, Docker deployment,
authentication layer, job queue, or durable result storage. Do not reintroduce those systems
unless the user explicitly changes the product scope.

## Code discovery

Use the `code-review-graph` tools before broad text or file searches when the graph service
is available:

| Tool | Use |
|---|---|
| `semantic_search_nodes_tool` | Find functions, classes, tests, and concepts |
| `get_architecture_overview_tool` | Understand module and community boundaries |
| `detect_changes_tool` | Review changed symbols and their risk |
| `get_review_context_tool` | Obtain focused source and dependency context |

If the graph tool reports a transport, indexing, or coverage failure, say so briefly and
fall back to targeted `rg`, `git diff`, and focused reads. Do not pretend a failed graph
query returned evidence.

## Change discipline

- Work on `main`; do not switch branches or disturb unrelated user changes.
- Inspect the nearest implementation, contract, and tests before editing.
- Make the smallest coherent change and avoid speculative abstractions.
- Use `uv` with the locked Python 3.12 dependency set.
- Keep uploads and results session-only. Never log or persist document contents or secrets.
- Prefer Windows user environment variables `OPENAI_API_KEY` and `OPENAI_BASE_URL`.
  `.env` and `.streamlit/secrets.toml` are ignored local fallbacks only.
- Update relevant documentation after every user-visible code change.
- Keep `.codegraph/`, `.code-review-graph/`, `.ua/`, and `graphify-out/` trackable. Ignore
  only their transient runtime/cache files already identified by the repository.

## Observable behavior to preserve

- Inputs: PDF, PNG, JPEG, WebP, TIFF, BMP, DOCX, PPTX, XLSX, ODT, ODP, ODS, and CSV.
- Limits: 200 MB, 500 pages, bounded PDF canvas area, and bounded decoded image pixels.
- Encrypted PDFs are rejected.
- Native PDF pages and Office files use Docling locally.
- Scanned PDF pages and images require OpenAI vision.
- Mixed PDFs route each page independently.
- The UI exposes Output, Annotated PDF, Markdown, and JSON views plus downloads.
- Fast, Balanced, and Audit map to `paperplane-ade-fast-latest`, `paperplane-ade-latest`,
  and `paperplane-ade-audit-latest`, respectively.
- The app binds to `127.0.0.1` and retains only the current Streamlit session state.

## Verification

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

For UI changes, run `uv run streamlit run streamlit_app.py`. For generated documentation,
run `uv run python scripts/build_handbook.py` and
`uv run python scripts/build_app_guide.py`.
