# Explanation: why two JSON contracts

Every Parse result has two exports: strict **ADE v2-style** JSON and
**`paperplane.parse.v5`** JSON. They serve different consumers, and the code keeps their
boundaries explicit.

## What each export optimizes for

The ADE v2-style export (`to_ade_v2_parse`, `paperplane/ade_contracts.py:149-234`)
is deliberately minimal: `markdown`, `metadata`, and a `structure` tree with
zero-based, per-type node IDs and inline `grounding`. It exists so that tooling
written against a documented-style ADE Parse response shape has something
stable to parse. It excludes Paperplane-specific concepts such as calibration status, raw
observed words, and cross-page relations.

The v5 export (`to_paperplane_export`, lines 237-271) wraps that same ADE
structure and adds everything Paperplane knows that the v2 shape has no room
for: `provenance`, a flat `words` list of individually observed native/OCR
words with `confidence_kind`, inferred cross-page `relations`, `warnings`, and
per-model token usage. A consumer that wants "just the compatible shape" reads
`v5.ade` and ignores the rest; one that wants full observability reads the
whole v5 document.

Keeping them as two named contracts (`ADEParseResponse` vs.
`PaperplaneParseExport`, distinguished by the v5 export's own
`contract: "paperplane.parse.v5"` discriminator field) separates the stable interop fields
from the Paperplane extension fields. A merged schema would add fields that can break simple
ADE-shaped parsers or require the richer data to be reconstructed from a flatter structure.

## What "ADE-compatible" means here

The README's "Outputs and contracts" section defines the boundary: "ADE-compatible"
describes Paperplane's versioned Python/Pydantic and JSON contracts and durable job
semantics. Paperplane does not call LandingAI's API, promise a drop-in replacement, or claim
LandingAI's accuracy numbers. It is "an independent implementation" inspired by LandingAI
ADE's observable Parse workflow and evidence model, and does not reimplement its API surface.

Concretely, that means:

- The ADE v2-style shape here (`markdown` / `metadata` / `structure`) mirrors
  the *documented style* of an ADE Parse response closely enough for tooling
  built against that style of contract to read it. Each field's
  semantics (ID numbering, `range_units`, `billing`, `openapi_spec` string) is
  defined by Paperplane's own `ade_contracts.py`, not by calling out to an
  external service.
- Nothing about "ADE v2 compatible" implies numeric parity with LandingAI's
  DPT-2 DocVQA benchmark score. Paperplane's own `docs/QUALITY.md` and
  benchmark manifest publish only measurements taken against Paperplane's own
  outputs.

The two exports keep the supported contract shape and job semantics separate
from Paperplane-specific fields. Consumers can use the documented-style shape
or read the full Paperplane export.

See also: [Reference: ADE JSON schema](../reference/ade-json-schema.md).
