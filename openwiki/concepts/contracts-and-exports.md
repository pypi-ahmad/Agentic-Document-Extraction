---
type: Data Contract
title: Grounding, contracts, and exports
description: The internal ParseResponse structure, grounding validation, ADE v2-style export, Paperplane v5 extensions, and downloadable output formats.
tags: [contracts, grounding, exports]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-622d077668845732e7510c74
    resource: repo://paperplane/ade_contracts.py
  - id: openwiki-source-e6e4dfe11c3b4c12b3595db1
    resource: repo://paperplane/contracts.py
  - id: openwiki-source-8190421d169b19f41436a695
    resource: repo://paperplane/outputs.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Grounding, contracts, and exports

## Internal ParseResponse

A `ParseResponse` contains document Markdown, metadata, a document-to-page-to-block structure, and an optional list of observed grounded words. Content blocks carry page identity, semantic role, ranges into the Markdown, and normalized boxes when their grounding status is `grounded`. A `semantic_only` block can have text ranges without a box. Table cells are children of table blocks and carry row and column coordinates.

`assemble_parse_response` joins page Markdown in physical order, inserts page-break comments between pages, and assigns one-based IDs by node type. It records each block's character span as it appends the Markdown. The response validator checks the root and page order, node IDs, block ownership, range bounds and ordering, atomic ranges within their parent, and exact text agreement for grounded words and atomic lines.

Ranges are half-open Unicode code-point offsets: use `markdown[start:end]` to recover the cited text. Boxes use normalized coordinates from 0 to 1. These values let consumers locate the evidence associated with a block; a box and a text range represent different kinds of location data.

## Two JSON exports

The ADE v2-style export converts the internal structure to a documented-style shape with `markdown`, `metadata`, and `structure`. It assigns zero-based IDs independently by node type, while internal IDs start at one. Its metadata declares `unicode_codepoints` as the range unit.

The `paperplane.parse.v5` export nests that ADE-shaped document under `ade` and adds Paperplane fields: the engine, provenance, observed word grounding, inferred relations, warnings, and per-model token usage. By default, word confidence is copied from raw observed confidence; the export function does not calibrate it. Relations are inferred from the selected parsed pages unless a caller supplies them.

## Other outputs

The Parse page exposes Markdown, sanitized HTML, annotated PDF, and both JSON views. Batch ZIP output can include each successful document's Markdown, HTML, annotated PDF, and two JSON files, along with a versioned manifest that records successful and failed documents. The archive builder derives safe output names from uploaded filenames. HTML output passes converted Markdown through an allowlist sanitizer before rendering or download.

## Related pages

- [Parse workflow and grounded assembly](../workflows/parse-document.md)
- [Organize workflows](../workflows/organize.md)
- [Processing engines, providers, and cost](../integrations/provider-catalog-and-cost.md)
