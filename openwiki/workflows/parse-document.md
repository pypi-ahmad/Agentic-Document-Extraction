---
type: Workflow
title: Parse workflow and grounded assembly
description: The path from upload checks and page selection through local or vision processing, grounded response validation, and downloadable outputs.
tags: [workflow, parsing, grounding, outputs]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-e6e4dfe11c3b4c12b3595db1
    resource: repo://paperplane/contracts.py
  - id: openwiki-source-6d19195abb4895053365adae
    resource: repo://paperplane/ingest.py
  - id: openwiki-source-8190421d169b19f41436a695
    resource: repo://paperplane/outputs.py
  - id: openwiki-source-c454053fe0ca1fd8d297ff5a
    resource: repo://paperplane/parser.py
  - id: openwiki-source-e145d6f0c3ed02aaf6b310dd
    resource: repo://paperplane/pipeline.py
  - id: openwiki-source-541a9e49a6db4313a22a5ad3
    resource: repo://paperplane/runtime.py
  - id: openwiki-source-964922c41d4be25ac5f159ec
    resource: repo://streamlit_app.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Parse workflow and grounded assembly

The Parse page captures selected uploads, engine settings, quality mode, model, and page ranges. It checks batch constraints before enabling **Parse files**, persists job metadata and the source files, runs the batch parser, builds output artifacts, and keeps results in the current Streamlit session.

## 1. Validate uploads and select pages

The parser accepts PDFs, images, and supported Office formats. It checks file size, type, page count, image pixel limits, encrypted PDFs, and PDF render-canvas dimensions. Office files are converted to PDF before inspection. Page ranges are one-based and inclusive; invalid or out-of-document ranges fail validation.

The UI accepts at most 20 files and 1 GiB combined per batch. The runtime runs up to six file parses concurrently and isolates failures per file, so a failed item is returned as an error outcome while other items can complete.

## 2. Choose the local or vision path

The UI offers Docling, PDF Inspector, cloud AI, or Ollama as the selected engine. Docling, PDF Inspector, and Ollama can also be followed by cloud enhancement. Local-only Docling and PDF Inspector parse locally. Cloud AI sends selected page images through the chosen provider adapter; Ollama sends them to the configured Ollama endpoint.

For `docling+cloud AI`, the parser runs Docling first and selects pages for refinement when confidence is missing or below the threshold, or when a page has no blocks. For `pdf-inspector+cloud AI`, it refines all selected pages when the inspector result is missing or low confidence; otherwise it refines pages marked as needing OCR or pages with no blocks. If Docling or PDF Inspector raises a `DocumentInputError` in an enhancement strategy, AI processes the selected pages. If enhancement fails on a page that has local blocks, the parser keeps that local output and records a warning. Failures in AI-only and Ollama strategies propagate to the per-file batch outcome.

Each vision-processed page is rendered to an image and passed to the structured page processor. Available text from preceding selected pages is included as context, capped to its last 6,000 characters, along with the current page's local context. The processor can request page reconciliation in Audit mode, or in Balanced mode when its quality check flags the draft; further checks depend on the selected mode and verification budget.

When a cloud response is interrupted by an OpenAI content filter, the page processor falls back to native PDF words, or local OCR when native words are absent. For GPT-6 Sol, excessive generated text is also replaced with locally observed words when available. These fallbacks retain warnings and source/verification metadata.

## 3. Assemble and validate the grounded response

The parser orders results by the selected physical pages and assembles page content into one Markdown document with page-break markers and a document-ID comment. The internal contract represents a document as pages, pages as blocks, and tables as nested cells. Each block carries source ranges and, where grounded, normalized page geometry; table cells carry row and column coordinates.

`ParseResponse` validates the Markdown character count, page order and IDs, block hierarchy, table-cell placement, ranges, and exact text for grounded words and atomic lines. After assembly, word grounding is added from native PDF words when available, otherwise from local OCR on a rendered page. Validation failures surface as per-file parse failures rather than a successful response with invalid ranges.

## 4. Build downloads and retain job artifacts

For each successful result, the UI builds an annotated PDF and offers Markdown, sanitized standalone HTML, Paperplane JSON, ADE v2 JSON, and a batch ZIP. The ZIP manifest records each source filename, completed or failed status, error, and the files included for that item. If annotated-PDF generation fails, the parse result remains available with an artifact error.

The page stores batch outcomes and previews in Streamlit session state. Separately, it saves job records, source files, Paperplane result JSON, and any annotated PDF in the local job store. See [job storage and lifecycle](../architecture/job-storage-and-lifecycle.md) for that retained history and its cleanup policy.

## Related pages

- [Contracts and exported formats](../concepts/contracts-and-exports.md)
- [Provider catalog and cost reporting](../integrations/provider-catalog-and-cost.md)
- [Tests, CI, and benchmark validation](../testing/CI-tests-and-benchmark.md)
