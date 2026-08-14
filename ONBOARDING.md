# Paperplane contributor onboarding

Paperplane is a local, stateless Streamlit application for converting PDFs, images, and
modern Office documents into context- and layout-aware Markdown, hierarchical grounding
JSON, and an annotated evidence PDF.

The active application is deliberately small: one Streamlit process and the `paperplane`
Python package. There is no database, REST API, background worker, JavaScript frontend,
Docker runtime, account system, or durable application storage.

## Start here

For normal Windows use, double-click `Paperplane.cmd`. It installs `uv` when needed,
installs Python 3.12.10, syncs locked dependencies, downloads Docling layout and table
models, and starts the app.
The local UI is available at `http://127.0.0.1:8551`.

For development:

```powershell
uv sync --locked --extra test --extra lint --extra docs
uv run streamlit run streamlit_app.py --server.port=8551
```

The key for the selected OpenAI or Agnes model is required for scanned PDFs and image
files. Native PDFs and modern Office files can be parsed locally without either key.

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
[Environment]::SetEnvironmentVariable("AGNES_API_KEY", "your-key", "User")
```

Open a new terminal after changing user-level variables. For a machine where user-level
variables are unavailable, copy `.env.example` to `.env`, or copy
`.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`. Never commit either local
file or a real credential.

## How the application works

```text
Streamlit upload
  -> validate type, size, page count, and image limits
  -> inspect each PDF page
  -> native page or Office file: local Docling parser
  -> scanned page or image: selected OpenAI or Agnes vision adapter
  -> assemble reading-order Markdown and hierarchical grounding JSON
  -> build an in-memory annotated evidence PDF
  -> display and download the current result
```

Mixed PDFs use both engines page by page. The three UI modes map to the following parser
models:

| UI mode | Parser model | Behavior |
|---|---|---|
| Fast | `paperplane-ade-fast-latest` | Luna draft with deterministic grounding |
| Balanced | `paperplane-ade-latest` | Adaptive verification for most documents |
| Audit | `paperplane-ade-audit-latest` | Highest inspection and repair budget |

Those behavior labels describe the OpenAI path. With Agnes selected, `agnes-2.5-flash`
fills every model-call role while Fast, Balanced, and Audit still control how much
verification work is allowed.

## Repository map

| Path | Purpose |
|---|---|
| `streamlit_app.py` | UI, session state, previews, result views, and downloads |
| `paperplane/runtime.py` | In-process construction of Docling and the selected AI adapter |
| `paperplane/agnes_document.py` | Agnes 2.5 Flash Chat Completions adapter |
| `paperplane/parser.py` | Validation, per-page routing, and response assembly |
| `paperplane/docling_parser.py` | Local native-document conversion |
| `paperplane/pipeline.py` | Scanned-page vision extraction and verification |
| `paperplane/contracts.py` | Public Markdown, hierarchy, range, and grounding contracts |
| `paperplane/annotated_pdf.py` | Source overlays and semantic-only evidence reports |
| `tests/` | Unit, contract, routing, UI, and artifact tests |
| `docs/` | Architecture, setup, operations, quality, and generated guides |
| `Paperplane.cmd` | One-file Windows setup and launcher |

## Working agreement

- Work on `main`, preserving unrelated local changes.
- Use `uv`; do not add a second environment or package-management workflow.
- Keep the Streamlit-only, in-process architecture unless a requested feature requires a
  documented change in direction.
- Do not introduce databases, persistence, queues, API servers, or frontend frameworks for
  session-local behavior.
- Keep credentials in user environment variables or ignored local configuration.
- Update relevant documentation whenever observable code behavior changes. At minimum,
  check `README.md`, `CHANGELOG.md`, `docs/RELEASE_NOTES.md`, and the affected setup,
  architecture, capability, or limitation page.
- Keep `.codegraph/`, `.code-review-graph/`, `.ua/`, and `graphify-out/` available for
  versioning; only their documented transient cache/runtime files should be ignored.

Use the repository knowledge graph before broad file searches when it is available. If the
graph service is unavailable or stale, state that briefly and fall back to targeted `rg`
searches and focused file reads.

## Before handing off a change

Run the narrowest relevant test first, then the full verification set when the change can
affect application behavior:

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

For documentation or UI changes, also start Streamlit and inspect the affected workflow.
Generated documentation must remain synchronized:

```powershell
uv run python scripts/build_handbook.py
uv run python scripts/build_app_guide.py
```

Begin with [README.md](README.md), then read [the architecture guide](docs/ARCHITECTURE.md)
and [how the pipeline works](docs/how-it-works.md).
