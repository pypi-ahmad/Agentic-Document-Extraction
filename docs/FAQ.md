# FAQ

## Is Paperplane a Streamlit app?

Yes. Streamlit is the only web runtime. The UI calls the Python parser directly in the same
process.

## Do I need to install Python or uv first?

No on Windows 11. Double-click `Paperplane.cmd`; it installs `uv`, Python 3.12.10, locked
dependencies, and required Docling models. Initial setup requires internet access.

## Does Paperplane use LandingAI ADE?

No. Paperplane is inspired by ADE's observable document-output workflow, but uses its own
Docling and OpenAI pipeline and does not claim ADE model or benchmark parity.

## Does it have an API or database?

No. There is no REST API, database, queue, worker, or durable result store.

## Where is my document saved?

Paperplane keeps the upload, latest result, and annotated PDF in Streamlit session memory.
Selecting another file, choosing **New extraction**, closing the tab, or stopping the app
clears that state. A browser download is the user's explicit persistence action.

The launcher does install Python packages and Docling model weights on disk. Statelessness
applies to document and result data, not runtime dependencies.

## Which credentials are required?

`OPENAI_API_KEY` is required for scanned PDFs and images and enables figure descriptions in
native documents. Native text PDFs and supported Office files can run locally without it.
`OPENAI_BASE_URL` is optional and defaults to `https://api.openai.com`.

Configuration precedence is existing environment variables, `.env`, Streamlit secrets,
then the default URL. Local credential files are ignored by Git.

## Which inputs work?

PDF, PNG, JPEG, WebP, TIFF/TIF, BMP, DOCX, PPTX, XLSX, ODT, ODP, ODS, and CSV. Legacy
DOC/PPT/XLS, RTF, encrypted PDFs, and password-protected files are unsupported.

## What happens with a mixed PDF?

Paperplane classifies each page independently. Native pages use Docling, scan-like pages
use OpenAI vision, and results are merged into original page order.

## What do Fast, Balanced, and Audit change?

Fast uses Luna with deterministic grounding and no Terra pass. Balanced applies Terra to
flagged content. Audit uses the highest rendering, verification, and repair budget.

## Which result views are available?

The UI provides rendered Output, Annotated PDF, raw Markdown, and JSON tabs. PDF/image
annotations overlay source pages. Office sources without physical geometry receive a
semantic evidence PDF. Annotated PDF, Markdown, and JSON are downloadable.

## Why can a large document take time?

Parsing is synchronous and vision pages are processed sequentially. Higher modes can make
additional model calls. There are no background jobs or resume support.

## Can I host it for multiple users?

Not with the checked-in configuration. Paperplane is local-only and binds to `127.0.0.1`.
A shared service would require authentication, isolation, retention, observability, and
abuse-control work that is intentionally outside v4.1.
