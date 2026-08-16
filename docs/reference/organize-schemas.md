# Reference: Organize schemas

All models below are Pydantic models defined in `paperplane/ade_workflows.py` unless noted
otherwise. All three workflow entry points — `classify_document`, `split_document`,
`section_document` — take a `ParseResponse` (the Parse output, `paperplane/contracts.py:201`)
as their first argument and return one of the response models below.

## `ClassDefinition`

Input model. One entry per allowed class passed to `classify_document`/`split_document`.

`paperplane/ade_workflows.py:13-15`

| Field | Type | Default | Notes |
|---|---|---|---|
| `name` | `str` | — (required, min length 1) | Label assigned to matching pages. Also used as matching-keyword source. |
| `description` | `str` | `""` | Additional matching-keyword source. In the Organize UI this is always set equal to `name` (`app_pages/organize.py:48-50`); calling `classify_document` directly lets you set it independently. |

## `ClassifiedPage`

One entry in `ClassifyResponse.pages`.

`paperplane/ade_workflows.py:18-22`

| Field | Type | Notes |
|---|---|---|
| `page` | `int` | Page number from the source structure, or a 1-based fallback index if the page had none. |
| `label` | `str` | The matched (or fallback) class `name`. |
| `reason` | `str` | Either `"Matched source term: <term>"` or `"No deterministic keyword match; returned the first allowed class"`. |
| `ranges` | `list[CodepointRange]` | Grounded Markdown ranges covering this page's blocks. |

## `ClassifyResponse`

Return type of `classify_document`.

`paperplane/ade_workflows.py:25-27`

| Field | Type | Notes |
|---|---|---|
| `pages` | `list[ClassifiedPage]` | One entry per page in the document's structure. |
| `warnings` | `list[str]` | One entry per page that hit the no-match fallback: `"Page {n}: classification is a deterministic partial"`. |

## `SplitResult`

One entry in `SplitResponse.documents`.

`paperplane/ade_workflows.py:45-49`

| Field | Type | Notes |
|---|---|---|
| `label` | `str` | The class name this group of pages was classified as. |
| `pages` | `list[int]` | Page numbers grouped under this label, in document order. |
| `markdown` | `str` | Each page's Markdown slice, joined with an `\n\n<!-- PAGE BREAK -->\n\n` separator. |
| `ranges` | `list[CodepointRange]` | Concatenation of every grouped page's ranges. |

## `SplitResponse`

Return type of `split_document`. Internally, `split_document` calls `classify_document`
first and groups its `ClassifiedPage` results by `label` (`paperplane/ade_workflows.py:126-146`).

`paperplane/ade_workflows.py:52-54`

| Field | Type | Notes |
|---|---|---|
| `documents` | `list[SplitResult]` | One entry per distinct label that matched at least one page. |
| `warnings` | `list[str]` | Passed straight through from the internal classification step. |

## `SectionResult`

One entry in `SectionResponse.sections`.

`paperplane/ade_workflows.py:30-36`

| Field | Type | Notes |
|---|---|---|
| `title` | `str` | First line of the page's first grounded block's text, truncated to 160 characters; falls back to `"Untitled section"` if that text is empty. |
| `level` | `int` | Always `1` — `section_document` does not currently infer heading depth. |
| `section_number` | `int` | 1-based, incremented per detected section across the whole document. |
| `start_reference` | `str` | The `id` of the `StructureNode` block this section's title came from. |
| `page` | `int` | Page number, or a 1-based fallback index. |
| `ranges` | `list[CodepointRange]` | Ranges of the title block only, not the whole section body. |

## `SectionResponse`

Return type of `section_document`. Runs over every page in the structure; a page with no
grounded blocks at all is skipped (no section entry, no warning).

`paperplane/ade_workflows.py:39-42`

| Field | Type | Notes |
|---|---|---|
| `sections` | `list[SectionResult]` | One per page that had at least one grounded block. |
| `markdown` | `str` | The full document Markdown, copied through unchanged from the input `ParseResponse`. |
| `warnings` | `list[str]` | One entry per page whose first block was not a `title`/`heading` semantic role: `"Page {n}: no explicit heading; first grounded block used as a partial"`. |

## `sections.json` (downloaded file)

The **Section** tab's download button (`app_pages/organize.py:92-97`) writes
`SectionResponse.model_dump(mode="json")` directly to disk with two-space indentation. Its
shape is identical to the `SectionResponse` table above — there is no separate export
schema.

## Referenced shared types

Defined in `paperplane/contracts.py`, reused across all Organize responses.

| Type | Location | Notes |
|---|---|---|
| `CodepointRange` | `paperplane/contracts.py:70-78` | Half-open Unicode code-point offsets (`start`, `end`) into `ParseResponse.markdown`. `end >= start` is enforced by a validator. |
| `StructureNode` | `paperplane/contracts.py:102-119` | Document → page → block → table-cell hierarchy. Relevant fields for Organize: `id`, `type`, `page`, `semantic_role`, `children`. |
| `ParseResponse` | `paperplane/contracts.py:201-205` | Input to every Organize function: `markdown`, `metadata`, `structure`, `words`. |
