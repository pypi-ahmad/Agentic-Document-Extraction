# How it works

```text
upload
  -> validate type, integrity, size, page count, canvas, and decoded pixels
  -> inspect and route each page
     -> native PDF or Office: local Docling conversion
     -> scan or image: render -> Luna draft -> deterministic grounding
                       -> optional Terra reconciliation/crop verification
  -> merge pages in original reading order
  -> assemble Markdown and hierarchical JSON
  -> build an in-memory annotated evidence PDF
  -> display Output/PDF/Markdown/JSON and expose downloads
```

## Routing

PyMuPDF identifies native and scan-like PDF pages. A mixed PDF may use both engines.
Office/OpenDocument/CSV content uses Docling, while images use OpenAI vision. There is no
manual engine selector.

## Mode policy

- Fast: Luna draft, deterministic checks, no Terra pass.
- Balanced: Terra checks only when deterministic quality signals flag content.
- Audit: highest rendering, reconciliation, crop, and repair budget.

## Shared output

Both engines feed the same assembler. It creates reading-order Markdown and a validated
document → page → block → atomic-line/table-cell hierarchy. HTML tables preserve merged
cells. Half-open Unicode ranges connect JSON nodes to exact Markdown text. Physical boxes
are normalized with a top-left origin.

IDs are stable within the returned response only. Office blocks without trustworthy
geometry are labeled `semantic_only` with null boxes rather than invented coordinates.

## Evidence and state

PDF/image results receive labeled source overlays. Office content without physical
geometry receives a semantic evidence report. Artifact generation is isolated: if the PDF
builder fails, a valid Markdown/JSON parse remains available with a separate UI error.

Each parse creates and closes its own OpenAI HTTP client. The cached Docling converter holds
model resources only. Paperplane does not persist document bytes, model responses, results,
or generated artifacts.
