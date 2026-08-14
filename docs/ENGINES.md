# Processing engines

Paperplane selects Docling or vision automatically from the document. Users choose the AI
model for vision work and a processing mode.

## Local Docling engine

Docling handles text-native PDF pages, DOCX, PPTX, XLSX, ODT, ODP, ODS, and CSV. It
provides reading order, semantic elements, tables, and provenance where the source format
contains trustworthy geometry.

Native PDF blocks with provenance receive normalized boxes. Office blocks without physical
page geometry are returned as `semantic_only` with exact Markdown ranges and null boxes.
Figures are described with the selected AI model when its key is present; otherwise
Paperplane emits an explicit unavailable placeholder and warning.

## Cloud vision engines

PyMuPDF renders scanned PDF pages and Pillow normalizes image frames. The selected model
produces structured reading-order drafts. Deterministic code aligns native words when
available, transforms coordinates, suppresses duplicate regions, validates critical
content, and assembles evidence.

Balanced mode can reuse the selected model for flagged reconciliation and crop
verification. Audit mode uses the highest verification budget. Fast mode skips the
verification pass.

## Provider adapters

Paperplane uses provider-native structured-output APIs for OpenAI, xAI, Google Gemini,
Anthropic, and Agnes. The exact display names, API IDs, environment variables, and official
references are maintained in [MODELS.md](MODELS.md). The launcher refreshes provider keys
from the Windows user environment without printing them.

Each adapter normalizes its provider's usage fields into input, output, cached-input, and
cache-write token totals. The parser aggregates them for the UI cost estimate.

## Routing

PyMuPDF classifies each PDF page. A page is native when it contains meaningful selectable
text and is not dominated by a full-page raster image; otherwise it is vision-routed.
Mixed PDFs combine Docling and the selected vision model in original page order.

Images always require vision. Office/OpenDocument/CSV input always starts with Docling.
There is no runtime plugin system or local model server. The UI choices are the six models
in the fixed catalog.

`OPENAI_BASE_URL` can target an operator-controlled endpoint that implements the expected
OpenAI Responses API contract. The default is `https://api.openai.com`.
