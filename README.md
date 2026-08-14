# Paperplane

Paperplane 4.1.0 is a local Streamlit app that converts PDFs, document images, and modern
Office files into context- and layout-aware Markdown, hierarchical grounding JSON, and an
annotated evidence PDF. It is inspired by LandingAI ADE's document-output workflow, but it
runs its own local Docling and OpenAI-based pipeline.

Paperplane does not use a database, API server, background worker, JavaScript frontend, or
durable application storage. Uploads and generated results remain only in the current
Streamlit session unless the user explicitly downloads them.

## Run on Windows

Double-click `Paperplane.cmd`. On first use, the launcher:

1. installs `uv` if necessary;
2. installs Python 3.12.10;
3. creates the environment and installs locked dependencies;
4. downloads the required Docling layout and table models; and
5. starts Paperplane on the local machine.

Windows 11 and an internet connection are required for initial setup. OpenAI credentials
are required for scanned PDFs and images and enable figure descriptions in native
documents. Text-based PDFs and Office files can be parsed locally without an API key.

Set credentials as Windows user environment variables, then open a new terminal before
launching the app:

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
```

`Paperplane.cmd` refreshes these values directly from the current user's Windows
environment. It does not store the key. On another machine, ignored local fallbacks are
available:

- copy `.env.example` to `.env`; or
- copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.

Environment variables take precedence over those local files. Never commit a real key.

No GPU, Node.js, npm, Docker, database, or Visual Studio C++ build tools are required.

## Use Paperplane

1. Upload a supported document.
2. Select Fast, Balanced, or Audit mode.
3. Choose **Parse document**.
4. Inspect the Output, Annotated PDF, Markdown, and JSON tabs.
5. Download the annotated PDF, Markdown, or JSON when needed.

| Input | Engine |
|---|---|
| Text-based PDF pages | Local Docling |
| Scanned PDF pages | OpenAI vision |
| Mixed PDFs | Automatic per-page Docling/OpenAI routing |
| PNG, JPEG, WebP, TIFF, BMP | OpenAI vision |
| DOCX, PPTX, XLSX, ODT, ODP, ODS, CSV | Local Docling; OpenAI is optional for figures |

The default limits are 200 MB and 500 pages. Encrypted PDFs are not supported. Processing
is synchronous in the local Streamlit session.

## Output contract

The Markdown preserves reading order and layout-derived structure such as headings, lists,
tables, figures, forms, and checkboxes. The JSON includes document, page, block,
atomic-line, and table-cell structure with Markdown ranges and normalized page grounding.

For PDFs and images, the annotated PDF overlays grounded blocks on source pages. Office
documents without trustworthy source geometry receive an explicit semantic evidence report
instead of invented coordinates.

## Manual development setup

```powershell
uv sync --locked --extra test --extra lint --extra docs
uv run streamlit run streamlit_app.py
```

Verification:

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

Start with the [contributor onboarding guide](ONBOARDING.md),
[architecture](docs/ARCHITECTURE.md), [run guide](docs/RUN_APP.md),
[capabilities](docs/APP_CAPABILITIES.md), and [limitations](docs/LIMITATIONS.md).
