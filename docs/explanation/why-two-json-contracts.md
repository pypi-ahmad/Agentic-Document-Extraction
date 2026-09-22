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

## What "ADE-compatible" actually means here

The README is explicit about the boundary of this compatibility claim (see
`README.md`'s "Outputs and contracts" section): "ADE-compatible" describes
Paperplane's own versioned Python/Pydantic and JSON contracts and durable job
semantics: it does not mean Paperplane calls LandingAI's API, promises a
drop-in replacement for it, or inherits LandingAI's accuracy numbers. Paperplane
is, in the project's own words, "an independent implementation" inspired by
LandingAI ADE's observable Parse workflow and evidence model, not a
reimplementation of its API surface.

Concretely, that means:

- The ADE v2-style shape here (`markdown` / `metadata` / `structure`) mirrors
  the *documented style* of an ADE Parse response closely enough that tooling
  built against that style of contract can read it: but every field's
  semantics (ID numbering, `range_units`, `billing`, `openapi_spec` string) is
  defined by Paperplane's own `ade_contracts.py`, not by calling out to an
  external service.
- Nothing about "ADE v2 compatible" implies numeric parity with LandingAI's
  DPT-2 DocVQA benchmark score. Paperplane's own `docs/QUALITY.md` and
  benchmark manifest publish only measurements taken against Paperplane's own
  outputs.

Maintaining the honest, narrower framing: "compatible contract shape and job
semantics," not "compatible product": is why the two-export design stays
worth the extra file: it lets Paperplane be transparent about exactly how much
compatibility it is and isn't claiming, one field at a time.

See also: [Reference: ADE JSON schema](../reference/ade-json-schema.md).
