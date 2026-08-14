# Paperplane: zero-to-hero study handbook

This handbook explains Paperplane 4.1.0: a local, stateless Streamlit workspace inspired by
LandingAI ADE's document-to-Markdown workflow. Paperplane is an independent implementation;
it does not call LandingAI services or claim model or benchmark parity.

By the end, you should understand how to run the app, how documents are routed, how the
grounded output contract works, where state and trust boundaries live, and how to change and
release the repository safely.

## 1. Understand the product

Paperplane accepts:

- native, scanned, and mixed PDFs;
- PNG, JPEG, WebP, TIFF, and BMP images; and
- DOCX, PPTX, XLSX, ODT, ODP, ODS, and CSV files.

It produces three synchronized artifacts:

1. context- and layout-aware Markdown in source reading order, including HTML tables and
   explicit page breaks;
2. JSON describing document, page, block, atomic-line, and table-cell structure with exact
   Markdown ranges and grounding evidence; and
3. an annotated PDF that overlays grounded blocks on PDF/image pages or presents Office
   blocks as semantic evidence when physical coordinates do not exist.

The Streamlit UI presents four views of those artifacts: rendered Output, Annotated PDF,
raw Markdown, and JSON.

The active product deliberately has no database, REST API, background worker, queue,
account system, JavaScript frontend, Docker runtime, package publishing, or durable
application file store.

## 2. Run it on Windows

Double-click `Paperplane.cmd`. The single launcher:

1. installs `uv` when needed;
2. installs Python 3.12.10;
3. creates the environment and synchronizes locked dependencies;
4. downloads Docling's layout and table models; and
5. starts the local Streamlit app.

The first setup requires an internet connection. It does not require Node.js, npm, Docker,
a GPU, a database, or Visual Studio C++ build tools.

Set Windows user environment variables for scanned PDFs and images:

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
[Environment]::SetEnvironmentVariable("XAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("AGNES_API_KEY", "your-key", "User")
```

Open a new terminal after changing user-level variables. `Paperplane.cmd` also refreshes
these values directly from the current user's Windows environment before launch.

`OPENAI_BASE_URL` is an optional OpenAI-only override. Select one of the six models in the
[catalog](docs/MODELS.md); scans and images require its matching key. Native PDFs and
supported Office files can run locally without a provider key; figure descriptions are
then unavailable.

On a machine where user-level variables are impractical, use one ignored local fallback:

- copy `.env.example` to `.env`; or
- copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.

Existing environment variables take precedence, followed by `.env`, Streamlit secrets, and
the default base URL. Never commit a real credential.

## 3. Learn the user workflow

1. Choose a supported document.
2. Select Fast, Balanced, or Audit mode.
3. Select **Parse document**.
4. Inspect page count, block count, engine, duration, and warnings.
5. Review provider token totals and the expandable estimated-cost calculation.
6. Review the Output, Annotated PDF, Markdown, and JSON tabs.
7. Download the Markdown, annotated PDF, or JSON if the result should persist.
8. Choose **New extraction** to clear the current workspace.

PDFs and images are previewed before parsing. Office and spreadsheet content appears after
Docling has converted it into the generated Markdown.

## 4. Learn the routing decision

```text
uploaded bytes
  -> validate size, extension, integrity, and page limits
  -> inspect every PDF page
     -> meaningful selectable text and no dominant full-page raster: Docling
     -> otherwise: selected cloud vision model
  -> non-PDF Office/OpenDocument/CSV: Docling
  -> image: selected cloud vision model
  -> merge results in original reading order
```

A mixed PDF can use both engines. Pages are merged by their original one-based page number.
There is no manual engine selector because routing is derived from the document itself.

The final metadata reports the selected provider engine, `docling`, or `hybrid`.

## 5. Understand the processing modes

The UI labels map to stable Paperplane model names and internal processing policies:

| UI mode | Parser model | Vision behavior |
|---|---|---|
| Fast | `paperplane-ade-fast-latest` | One draft and deterministic grounding; no verification pass |
| Balanced | `paperplane-ade-latest` | Selected-model checks for flagged content |
| Audit | `paperplane-ade-audit-latest` | Highest rendering, verification, and repair budget |

The selected mode changes work performed on pixel-based content. Native Docling conversion
still follows the document's structure, although the selected AI model can describe
figures when its key is configured.

The selected model serves every model-call role. The mode bounds reconciliation,
verification, crop work, and repairs without changing the selected API model ID.

## 6. Understand the processing engines

### Docling path

Docling parses native content locally. Native PDF elements with provenance receive
normalized, top-left-origin boxes. Office elements without trustworthy physical geometry
receive `grounding_status: "semantic_only"`, a null box, and exact Markdown ranges.
Paperplane never invents coordinates merely to make a contract appear complete.

Tables are serialized as HTML so merged cells remain representable. Table-cell JSON records
zero-based `row` and `col` values plus `rowspan` and `colspan`.

Native-document figures use the selected AI model for a literal semantic description when its key is
available. Without a key—or if description fails—the figure remains in reading order with
an explicit “description unavailable” placeholder and a result warning.

### Cloud vision path

The selected model reads each rendered scan or image and proposes reading-order blocks,
tight normalized boxes, atomic visual lines, and table-cell coordinates. Deterministic code
then aligns native words when available, suppresses duplicates, validates critical tokens,
and builds evidence.

Balanced and Audit modes can reuse that model to reconcile a difficult page or verify a
focused crop. Vision pages are processed sequentially and bounded by the selected policy.
Provider-native adapters cover OpenAI and xAI Responses, Google Gemini `generateContent`,
Anthropic Messages, and Agnes Chat Completions. Every result passes through the same
deterministic grounding and Pydantic contract validation.

## 7. Understand the output contract

The Markdown is the human- and agent-readable content boundary. Adjacent physical pages are
separated by `<!-- PAGE BREAK -->`; a final `doc_id` comment supports traceability.

The JSON hierarchy is:

```text
document
  -> page
     -> block
        -> atomic line
        -> table cell
           -> atomic line
```

Important contract rules:

- physical PDF and image pages are one-based;
- logical Office content without physical pagination can have a null page number;
- physical boxes are normalized to the page and use top-left-origin coordinates;
- ranges use half-open Unicode code-point offsets;
- `markdown[start:end]` must reproduce the exact grounded text;
- table cells remain nested under their table block; and
- IDs are stable within one response, but are not promised to remain identical after a
  document is parsed again.

The response metadata includes source format, model, engine, duration, page count, output
character count, provider token usage, and non-fatal warnings. Streamlit uses those token
counts and the configured rates in `docs/MODELS.md` to estimate input, output, and total
cost. The estimate does not replace the provider invoice.

## 8. Understand the annotated PDF

For PDF and image sources, Paperplane overlays grounded blocks on the original or rendered
source pages. This lets a reviewer compare Markdown and JSON claims against visible evidence.

Office documents usually lack reliable source-page geometry. Their annotated PDF is
therefore a semantic evidence report listing blocks and IDs as `semantic_only`; it does not
pretend that invented boxes came from the source.

The artifact is built in memory after parsing. Failure to create it does not discard a
successful Markdown/JSON result; the UI reports the artifact error separately.

## 9. Understand privacy, state, and security

Streamlit keeps the uploaded bytes, latest result, and annotated PDF in the current session.
Choosing another file, starting a new extraction, closing the tab, or stopping the app ends
that application state. Downloading is the user's explicit persistence action.

Docling processing is local. Scanned pages, image files, and requested figure crops are sent
to the selected provider endpoint. Paperplane does not print,
commit, or deliberately persist the API key or document content.

The launcher still installs dependencies and model weights on disk; “stateless” describes
document and result data, not the Python environment or model cache.

Streamlit binds to `127.0.0.1`, keeps XSRF protection enabled, and disables Streamlit usage
telemetry. Rendered Markdown is sanitized before the UI allows its supported HTML tables.

## 10. Know the operational boundaries

- Maximum upload: 200 MB.
- Maximum document length: 500 pages or image frames.
- Maximum PDF page canvas area: 4,000,000 source-coordinate units.
- Maximum decoded image content: 40,000,000 pixels across frames.
- Processing is synchronous; there are no resumable or background jobs.
- Legacy DOC/PPT/XLS, RTF, encrypted PDFs, and password-protected documents are unsupported.
- Local Docling conversion does not OCR scanned pages; those require the selected cloud
  model and its credential.
- There is no schema extraction, async API, saved history, reusable schema store, or
  multi-user authentication.
- Extraction and grounding must be reviewed before high-impact use.

## 11. Follow the code

Read these files in order:

1. `streamlit_app.py` — upload, mode controls, preview, result tabs, and downloads.
2. `paperplane/runtime.py` — in-process construction of Docling and the selected AI adapter.
3. `paperplane/model_catalog.py` — supported model names, API IDs, and credential mapping.
4. `paperplane/openai_document.py` — OpenAI and xAI Responses boundary.
5. `paperplane/gemini_document.py` — Google Gemini `generateContent` boundary.
6. `paperplane/anthropic_document.py` — Anthropic Messages boundary.
7. `paperplane/agnes_document.py` — Agnes Chat Completions boundary.
8. `paperplane/ingest.py` — validation, PDF classification, and page rendering.
9. `paperplane/parser.py` — automatic routing, engine merge, and response metadata.
10. `paperplane/docling_parser.py` — native serialization, tables, figures, and provenance.
11. `paperplane/pipeline.py` — provider-neutral drafting, deterministic checks, and verification.
12. `paperplane/grounding.py` — coordinate transforms and native-word alignment.
13. `paperplane/contracts.py` — final Markdown assembly and contract validation.
14. `paperplane/annotated_pdf.py` — source overlays and semantic evidence reports.
15. `tests/` — executable examples of routing, contracts, configuration, UI, and artifacts.

The important design boundary is simple: Streamlit owns interaction and session state;
`paperplane` receives bytes and returns validated Python values without saving them.

## 12. Make changes safely

- Work on `main` while preserving unrelated user changes.
- Keep parser and document logic independent from Streamlit widgets.
- Validate untrusted uploads at the parser boundary.
- Never cache document bytes, results, or secrets. Caching the Docling converter is safe
  because it retains model resources, not user documents.
- Preserve the single automatic routing path unless the product contract explicitly changes.
- Use `uv` and the locked Python 3.12 dependency set.
- Add focused tests for every changed contract or behavior.
- Update all affected documentation after every code change, including this handbook,
  `README.md`, `CHANGELOG.md`, and the relevant page under `docs/`.
- Keep `.codegraph/`, `.code-review-graph/`, `.ua/`, and `graphify-out/` available for
  versioning; ignore only their transient runtime/cache files.

Use the repository knowledge graph before broad searches when it is available. If the graph
service is unavailable, state that and use focused `rg` searches and file reads.

## 13. Understand documentation and releases

Paperplane publishes source-only GitHub releases. It is not published to PyPI. The release
script synchronizes only `pyproject.toml`, `streamlit_app.py`, and `CHANGELOG.md`; all other
documentation must already be correct before release.

Rebuild the generated guides after documentation changes:

```powershell
uv run python scripts/build_handbook.py
uv run python scripts/build_app_guide.py
```

Preview a patch release without modifying files:

```powershell
uv run python scripts/release.py --bump patch --dry-run
```

Publishing requires a clean `main` worktree and authenticated `gh`. See
[RELEASE.md](RELEASE.md) for the complete procedure.

## 14. Verify the repository

```powershell
uv sync --locked --extra test --extra lint --extra docs
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
uv run streamlit run streamlit_app.py --server.port=8551
```

The concise tutorial is [docs/ZERO_TO_MASTERY.md](docs/ZERO_TO_MASTERY.md). Continue with
the [model catalog](docs/MODELS.md), [architecture guide](docs/ARCHITECTURE.md),
[capability reference](docs/APP_CAPABILITIES.md), [run guide](docs/RUN_APP.md), and
[limitations](docs/LIMITATIONS.md).
