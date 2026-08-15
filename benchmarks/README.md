# Paperplane benchmarks

This directory defines the locked, versioned evaluation surface. The manifest pins every input by
SHA-256 and names every engine and metric. A result is publishable only when its raw outputs,
prompts, engine/model versions, timings, token counts, pricing snapshot, calibration corpus hash,
and failures are included in the result bundle.

The initial corpus contains the repository's attributed, MIT-licensed water-mailing sample; see
[`Sample-PDF/README.md`](../Sample-PDF/README.md). It is deliberately too small for an accuracy
claim. Add only redistributable scans, forms, columns, Office documents, sections, tables, and
cross-page continuations with ground truth before publishing comparative scores.

Paperplane does not reuse LandingAI's reported 99.16% DocVQA result and does not claim accuracy
parity with ADE. Missing runs remain missing; they are never scored as zero or silently excluded.
