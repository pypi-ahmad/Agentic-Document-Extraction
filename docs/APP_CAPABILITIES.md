# Paperplane capabilities

Paperplane 5.1.0 is a private multipage Streamlit workspace for converting PDFs, images,
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
- Ollama discovery includes every installed model and checks the reported `vision`
  capability before enabling Parse.
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

Parse, Organize, Jobs, and Benchmarks are separate pages. SQLite job metadata and
private artifacts are stored under `%LOCALAPPDATA%\Paperplane` for seven days. Users can
cancel job state, delete one job, or clear all retained jobs.

Parse configuration appears vertically in the sidebar. One main-canvas document selector
drives Input preview, Output, Annotated PDF, Markdown, HTML, and JSON tabs. Selected-document
downloads sit in one responsive row. The batch ZIP contains all successful documents'
available outputs and a versioned success/failure manifest, but no original uploads.
The checked-in Streamlit theme uses near-black surfaces, charcoal panels, and red accents.
Within that dark workspace, HTML results use a responsive, print-friendly white paper
surface with black text. The preview, individual HTML download, and ZIP copy match.

There is no public/local HTTP API in v5. ADE compatibility refers to versioned JSON and
Pydantic contracts and async/durable job semantics, not a client drop-in claim.
