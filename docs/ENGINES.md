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

## OpenAI vision engine

PyMuPDF renders scanned PDF pages and Pillow normalizes image frames. `gpt-5.6-luna`
produces structured reading-order drafts. Deterministic code aligns native words when
available, transforms coordinates, suppresses duplicate regions, validates critical
content, and assembles evidence.

Balanced mode can use `gpt-5.6-terra` for flagged reconciliation and crop verification.
Audit mode uses the highest verification budget. Fast mode does not run Terra.

## Agnes 2.5 Flash vision engine

Agnes uses the official `agnes-2.5-flash` Chat Completions endpoint. The same model fills
the pipeline's draft and verification roles, using JSON-only instructions followed by the
same deterministic validation and grounding. It reads `AGNES_API_KEY`; the launcher
refreshes that key from the Windows user environment without printing it.

See the official [Agnes 2.5 Flash model guide](https://www.agnes-ai.com/en/docs/agnes-25-flash)
and [Agnes API overview](https://www.agnes-ai.com/en/docs/overview).

## Routing

PyMuPDF classifies each PDF page. A page is native when it contains meaningful selectable
text and is not dominated by a full-page raster image; otherwise it is vision-routed.
Mixed PDFs combine Docling and the selected vision model in original page order.

Images always require vision. Office/OpenDocument/CSV input always starts with Docling.
There is no runtime plugin system or local model server. The UI provider choices are
OpenAI Luna/Terra and Agnes 2.5 Flash.

`OPENAI_BASE_URL` can target an operator-controlled endpoint that implements the expected
OpenAI Responses API contract. The default is `https://api.openai.com`.
