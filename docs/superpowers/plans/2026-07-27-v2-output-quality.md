# V2 Output Quality Implementation Plan

**Goal:** Restore all extracted page content, suppress duplicate regions, reject malformed visual Markdown, and prevent partial-document assembly.

**Approach:** Render every surviving chunk regardless of hierarchy. Strengthen deterministic reconciliation before adding model work, tighten existing prompts and crop validation, then invalidate V2 page caches. Keep public API and document schema unchanged.

## Acceptance

- Parented chunks remain hierarchical in JSON and appear once in Markdown with valid spans.
- Spatially overlapping near-equal or contained duplicate text collapses across semantic types; distinct content remains.
- Figure and chart chunks contain semantic `<figure>` and `<description>` markup or an unresolved placeholder.
- Assembly accepts exactly pages `1..page_count` and rejects missing or mismatched page results.
- Stored-run replay reaches strict accuracy >= 0.70, token F1 >= 0.90, and minimum-page accuracy >= 0.55.
- One new Balanced run improves on strict `0.3178` and token F1 `0.7675`, with eight substantive pages and no listed report defects.

## Tasks

1. Add failing unit regressions for child rendering, duplicate containment, malformed visuals, and page gaps.
2. Implement minimal shared fixes in reconciliation, page processing, and assembly.
3. Bump prompt/schema/page-result cache version from `v7` to `v8`.
4. Run targeted and full verification, offline replay, then one paid Balanced extraction.

## Constraints

- No new dependency, database migration, external API change, commit, or push.
- Preserve unrelated dirty-worktree changes.
- No final full-document model rewrite.
