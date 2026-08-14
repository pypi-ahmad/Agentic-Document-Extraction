# How Paperplane works

```text
upload up to 20 files
  -> choose exactly one engine (all are off initially)
  -> validate type, size, and each page range
  -> process up to six files concurrently; files remain isolated
  -> keep selected pages in physical reading order
  -> Docling / PDF Inspector / Cloud AI / Ollama
     -> optional cloud enhancement for local engines
  -> assemble global Markdown, blocks, atomic lines, cells, and citations
  -> align native-PDF or RapidOCR-observed words; omit unmatched words
  -> infer section, repeated marginalia, table continuation, and range-boundary relations
  -> export strict ADE v2-style JSON and Paperplane v5 JSON
  -> render sanitized HTML on a responsive white paper surface and package it in a manifest ZIP
  -> optionally Classify, Split, or Section in Organize
  -> retain local job metadata and artifacts for seven days
```

Pages outside a range are never rendered, parsed, or placed in context. For AI processing,
later selected pages can receive bounded Markdown context from earlier selected pages. This
supports document-level continuity without leaking content between uploaded files.
Cloud providers receive only selected page images. Agnes receives those PNGs inline rather
than through public image URLs.

Strict ADE output uses zero-based response-local type IDs and inline normalized grounding.
Paperplane output adds observed words, confidence state, provenance, warnings, and semantic
relations. Organize workflows retain source ranges and identify deterministic partials.

Job execution has a durable service boundary and checkpoint files, but no HTTP endpoints in
v5. The UI directly calls Python services in the same Streamlit process.

The Parse sidebar owns engine, model, upload, and page-range controls. A single selected
document drives six full-width main views. Individual downloads always follow that
selection; the batch archive covers all outcomes and lists failures only in its manifest.
The HTML view and exported HTML use the same black-on-white, print-friendly presentation;
the surrounding Streamlit workspace remains red/black.
