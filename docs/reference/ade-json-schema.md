# Reference: ADE v2 and Paperplane v5 JSON schema

Both exports are produced from an internal `ParseResponse`
(`paperplane/contracts.py:201-205`) by two functions in
`paperplane/ade_contracts.py`: `to_ade_v2_parse` (lines 149–234) builds the ADE
v2-style export, and `to_paperplane_export` (lines 237–271) wraps it into the
richer v5 export.

## ADE v2-style export (`ADEParseResponse`)

Source: `paperplane/ade_contracts.py:104-109`.

| Field | Type | Notes |
|---|---|---|
| `markdown` | `str` | Full document Markdown, in reading order, with page breaks. |
| `metadata` | `ADEParseMetadata` | See table below. |
| `structure` | `ADEStructureNode` | Root node, always `id="document-0"`, `type="document"` (`ade_contracts.py:233`). |

### `metadata` (`ADEParseMetadata`, `ade_contracts.py:92-101`)

| Field | Type | Notes |
|---|---|---|
| `job_id` | `str` | Copied from the internal `ParseMetadata.job_id`. |
| `model_version` | `str` | Defaults to `"paperplane-5.0.0"` (`to_ade_v2_parse` keyword default, line 152). |
| `page_count` | `int` | `source_page_count` if set, else `page_count` (line 218). |
| `output_markdown_chars` | `int` | `len(markdown)`, computed at export time (line 225). |
| `range_units` | `"unicode_codepoints"` | Fixed literal. |
| `openapi_spec` | `str` | Fixed literal `"paperplane://contracts/ade-v2-parse/5.0.0"`. |
| `failed_pages` | `list[int]` | Copied from `ParseMetadata.failed_pages`. |
| `duration_ms` | `int \| None` | Copied from `ParseMetadata.duration_ms`. |
| `billing` | `ADEBilling` | `{service_tier, total_credits}`; `service_tier` defaults to `"local"` when unset (line 229). |

### `structure` (`ADEStructureNode`, `ade_contracts.py:73-84`)

| Field | Type | Notes |
|---|---|---|
| `id` | `str` | `"<type>-<index>"`, **zero-based**, assigned per node type in document order (`node_id()`, lines 158–161). E.g. the first two text blocks are `text-0`, `text-1`. This differs from the internal `ParseResponse.structure`, whose IDs are **one-based** (`contracts.py:245`, `document-1`, `page-1`, `text-1`, ...) — the v2 export re-numbers everything from zero when it converts. |
| `type` | `str` | One of the `StructureType` values from `contracts.py:20-32` (`document`, `page`, `text`, `table`, `table_cell`, `figure`, `marginalia`, `attestation`, `logo`, `card`, `scan_code`). |
| `grounding` | `ADEGrounding \| None` | `None` on the `document` root; present on `page` and content nodes. |
| `atomic_grounding` | `list[ADEGrounding] \| None` | Per-line grounding; suppressed (empty) for plain `table` nodes and set to `None` when empty for non-table-cell nodes (lines 178–184). |
| `status` | `"ok" \| "failed" \| None` | Only set on `page` nodes, `"failed"` if that physical page is in `metadata.failed_pages` (lines 202, 212). |
| `reason` | `str \| None` | `"Page processing failed"` when `status == "failed"`, else `None`. |
| `row`, `col`, `rowspan`, `colspan` | `int \| None` | Only meaningful on `table_cell` nodes. |
| `children` | `list[ADEStructureNode]` | Recursive; `document → page → block (→ table_cell)`. |

`ADEGrounding` (`ade_contracts.py:67-71`): `{page: int, range: {start, end}, box: {xmin, ymin, xmax, ymax}}`.
`range` values are half-open Unicode code-point offsets into the top-level
`markdown` string (`contracts.py:70-80`); `box` coordinates are normalized to
`[0, 1]` (`contracts.py:55-61`).

## Paperplane v5 export (`PaperplaneParseExport`)

Source: `paperplane/ade_contracts.py:121-129`.

| Field | Type | Notes |
|---|---|---|
| `contract` | `"paperplane.parse.v5"` | Fixed literal discriminator. |
| `ade` | `ADEParseResponse` | The full ADE v2-style export described above, nested. |
| `engine` | `str` | Copied from `ParseResponse.metadata.engine` (e.g. `"docling"`, `"pdf_inspector"`, `"openai_vision"`). |
| `provenance` | `dict[str, Any]` | Caller-supplied; empty `{}` unless the caller of `to_paperplane_export` passes one. |
| `words` | `list[WordGrounding]` | See below. Defaults to one entry per `ParseResponse.words` item when the caller does not pass its own list (lines 244–262). |
| `relations` | `list[dict[str, Any]]` | Cross-page relations from `paperplane.document_intelligence.infer_document_relations` unless the caller overrides them (line 268). |
| `warnings` | `list[str]` | Copied from `ParseMetadata.warnings`. |
| `model_usage` | `dict[str, ModelTokenUsage]` | Copied from `ParseMetadata.model_usage`; each value has `input_tokens`, `output_tokens`, `cached_input_tokens`, `cache_write_tokens` (`contracts.py:143-147`). |

### `words[]` (`WordGrounding`, `ade_contracts.py:112-118`)

| Field | Type | Notes |
|---|---|---|
| `text` | `str` | The observed word text. |
| `grounding` | `ADEGrounding` | Same shape as above. |
| `confidence` | `float \| None` | `[0, 1]`. In the default construction path this is `word.raw_confidence` from `GroundedWord` (`contracts.py:99`, `ade_contracts.py:259`) — **not** run through calibration. |
| `confidence_kind` | `"calibrated" \| "raw_uncalibrated"` | Defaults to `"raw_uncalibrated"` (line 118) and is **never set to `"calibrated"` by `to_paperplane_export` itself** — as of this checkout, nothing in `paperplane/` calls `calibration.confidence_for` to populate this field automatically (confirmed by a repo-wide search for `confidence_for`, whose only call site is its own definition). A caller wanting calibrated values must call `confidence_for` (`paperplane/calibration.py:37-51`) itself and construct `WordGrounding` entries with the result, passing them via `to_paperplane_export(..., words=...)`. |

## Where the source data comes from

`ParseResponse` (`contracts.py:201-205`) — the object both exports are derived
from — is itself assembled deterministically by
`assemble_parse_response` (`contracts.py:348-503`) from page-agent
observations, or produced by the Docling/PDF Inspector parsers. Its own
validators (`contracts.py:207-276`) enforce, at construction time, that every
`range` and `atomic_grounding` range slices back to matching Markdown text —
this is why grounding is guaranteed to align exactly in both JSON exports
derived from it, rather than being a best-effort convention.

See also: [Explanation: why two JSON contracts](../explanation/why-two-json-contracts.md),
[How to extract grounding and confidence](../how-to/extract-grounding-and-confidence.md).
