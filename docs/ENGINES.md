# Processing engines

Paperplane selects its engine automatically from the document. Users choose a processing
mode, not a parser implementation.

## Local Docling engine

Docling handles text-native PDF pages, DOCX, PPTX, XLSX, ODT, ODP, ODS, and CSV. It
provides reading order, semantic elements, tables, and provenance where the source format
contains trustworthy geometry.

Native PDF blocks with provenance receive normalized boxes. Office blocks without physical
page geometry are returned as `semantic_only` with exact Markdown ranges and null boxes.
Figures are described with OpenAI when a key is present; otherwise Paperplane emits an
explicit unavailable placeholder and warning.

## OpenAI vision engine

PyMuPDF renders scanned PDF pages and Pillow normalizes image frames. `gpt-5.6-luna`
produces structured reading-order drafts. Deterministic code aligns native words when
available, transforms coordinates, suppresses duplicate regions, validates critical
content, and assembles evidence.

Balanced mode can use `gpt-5.6-terra` for flagged reconciliation and crop verification.
Audit mode uses the highest verification budget. Fast mode does not run Terra.

## Routing

PyMuPDF classifies each PDF page. A page is native when it contains meaningful selectable
text and is not dominated by a full-page raster image; otherwise it is vision-routed.
Mixed PDFs combine Docling and OpenAI results in original page order.

Images always require vision. Office/OpenDocument/CSV input always starts with Docling.
There is no runtime plugin system, local model server, manual engine selector, or alternate
provider selector.

`OPENAI_BASE_URL` can target an operator-controlled endpoint that implements the expected
OpenAI Responses API contract. The default is `https://api.openai.com`.
