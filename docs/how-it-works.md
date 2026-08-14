# How it works

```text
upload
  -> validate type, integrity, size, page count, canvas, and decoded pixels
  -> inspect and route each page
     -> native PDF or Office: local Docling conversion
     -> scan or image: render -> selected OpenAI or Agnes model
                       -> deterministic grounding and mode-driven verification
  -> merge pages in original reading order
  -> assemble Markdown and hierarchical JSON
  -> build an in-memory annotated evidence PDF
  -> display Output/PDF/Markdown/JSON and expose downloads
```

## Routing

PyMuPDF identifies native and scan-like PDF pages. A mixed PDF may use both engines.
Office/OpenDocument/CSV content uses Docling, while images use the AI model selected in the
UI.

## Mode policy

- Fast: one draft plus deterministic checks; OpenAI skips Terra.
- Balanced: additional model checks only when deterministic signals flag content.
- Audit: highest rendering, reconciliation, crop, and repair budget.

OpenAI maps draft and verification work to Luna and Terra. Agnes maps every model call to
`agnes-2.5-flash`; the processing policy remains unchanged.

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

Each parse creates and closes its own provider HTTP client. The cached Docling converter holds
model resources only. Paperplane does not persist document bytes, model responses, results,
or generated artifacts.
