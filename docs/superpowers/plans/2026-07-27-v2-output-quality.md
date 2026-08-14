# Archived plan: V2 output quality

## Status

Completed in concept and superseded in implementation by Paperplane 4.2.1. The former API,
stored-run replay, page cache, and benchmark tasks are not part of the current product.

## Original intent

The plan aimed to preserve extracted content, suppress duplicate regions, reject malformed
visual output, validate complete page assembly, and improve grounded Markdown quality.

## Current v4.2.1 result

- Docling and every selectable vision-provider path feed one validated Markdown/JSON assembler;
- duplicate suppression and reading-order reconciliation are deterministic;
- tables retain hierarchy and merged-cell metadata;
- figures use semantic descriptions or explicit unavailable placeholders;
- Markdown ranges, page ordering, boxes, and atomic evidence are validated;
- annotated source overlays make grounding reviewable; and
- tests cover reconciliation, contracts, page routing, and evidence artifacts.

Recipe version `v9` is internal implementation state, not a public cache or API contract.
No stored replay benchmark or accuracy-parity claim is currently published.
