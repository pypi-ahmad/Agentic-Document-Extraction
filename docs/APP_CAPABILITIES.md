# Paperplane capabilities

Paperplane 5.2.0 is an open-source, local-first multipage Streamlit workspace for converting PDFs, images,
and modern Office files into reading-order Markdown, grounded JSON, annotated PDFs, and
cited downstream data.

## Processing

- Up to 20 files per batch, 1 GiB combined, six concurrent files, and 200 MiB/500 pages per
  file.
- Independent one-based inclusive page range per file. Pages outside the range are not
  inspected.
- Four explicit, mutually exclusive engines, initially all off: Docling ADE, PDF Inspector
  ADE, Cloud AI ADE, and Ollama ADE.
- Optional cloud enhancement after Docling, PDF Inspector, or Ollama; no automatic routing.
- Agnes 2.5 Flash supports private visual Parse and enhancement through inline PNG input;
  uploads do not require public image URLs.
- Agnes structured results accept schema tool calls or JSON content, normalize equivalent
  0–1000 boxes and omitted nullable chunk fields, then apply local geometry validation and
  one bounded correction attempt so valid regions reach annotated PDFs.
- Ollama discovery includes every installed model and checks the reported `vision`
  capability before enabling Parse.
- GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR use CPU PP-DocLayoutV3 regions, native crop
  prompts, detector-box grounding, and bounded output cleanup. DeepSeek retries one empty
  or transiently failed text region, exposes skipped regions as warnings, and stops after
  three consecutive failures. RapidOCR is used only for final exact word-box alignment.
- Gemini uses `GOOGLE_API_KEY`, with legacy `GEMINI_API_KEY` fallback, and exposes Gemini
  3.5 Flash-Lite plus Gemini 3.7 Flash.
- Prior selected-page context, ordered assembly, section starts, repeated marginalia, and
  conservative continued-table relationships.
- Idempotent one-file setup and launch on Windows and Linux.

## Evidence and contracts

- Markdown, annotated PDF, strict ADE v2-style Parse JSON, and richer
  `paperplane.parse.v5` JSON, plus sanitized standalone HTML.
- Document → page → block → atomic-line/table-cell hierarchy with normalized boxes and
  half-open Unicode ranges.
- Native-PDF and RapidOCR word boxes only when observed words exactly align to Markdown.
- Raw confidence remains visibly uncalibrated unless an engine/model/version profile and
  corpus hash match.
- Cited Classify, Split, and Section deterministic workflows.

## Workspace and retention

Parse, Organize, Jobs, and Cost are separate pages. SQLite job metadata and
private artifacts are stored under `%LOCALAPPDATA%\Paperplane` for seven days. Users can
cancel job state, delete one job, or clear all retained jobs.

Uploads, Parse outputs, Organize values, and selections remain available while navigating
inside one browser session. Cost accumulates successful provider-reported input,
cached-input, and output tokens by model and applies the configured rates. Free and local
models remain visible with $0 API cost.

Parse configuration appears vertically in the sidebar. One main-canvas document selector
drives Input preview, Output, Annotated PDF, Markdown, HTML, and JSON tabs. Selected-document
downloads sit in one responsive row. The batch ZIP contains all successful documents'
available outputs and a versioned success/failure manifest, but no original uploads.
During processing, one batch-wide bar reports the active document/page or output stage and
a monotonic percentage. It reaches 100% after job metadata is saved, including batches with
failed documents; it is a completed-work indicator rather than a remaining-time estimate.
The checked-in Streamlit theme uses near-black surfaces, charcoal panels, and red accents.
Within that dark workspace, HTML results use a responsive, print-friendly white paper
surface with black text. The preview, individual HTML download, and ZIP copy match.

There is no public/local HTTP API in v5. ADE compatibility refers to versioned JSON and
Pydantic contracts and async/durable job semantics, not a client drop-in claim.

## Open-source operation

Paperplane is MIT-licensed and intended to run on the operator's own machine. Operators
provide any cloud credentials they choose to use and are responsible for their files,
permission to process them, provider terms and charges, compliance obligations, output
review, and retained-data deletion. Local engines keep content local; Cloud AI and cloud
enhancement send selected pages to the chosen provider.
