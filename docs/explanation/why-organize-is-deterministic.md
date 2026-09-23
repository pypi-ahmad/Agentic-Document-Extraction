# Why Organize is deterministic

Classify, Split, and Section run as Python over an already-parsed document. They make no
second model call, and each result traces to a page and character range in the Parse output.

## What "deterministic" means here

`paperplane/ade_workflows.py` holds the entire implementation, and it has no dependency on
any AI provider module. Given the same `ParseResponse` and the same class list, calling
`classify_document`, `split_document`, or `section_document` again always produces the same
output. The behavior is fully described by:

- `_class_for_text` (`paperplane/ade_workflows.py:70-79`): a keyword-substring match over
  class name/description terms, ordered and first-match-wins.
- `section_document` (`paperplane/ade_workflows.py:101-123`): a per-page rule: use the
  first grounded block as the section title, and flag it as a partial when that block is not
  already marked `title`/`heading`.
- `split_document` (`paperplane/ade_workflows.py:126-146`): reuses `classify_document` and
  regroups its output; it adds no new logic of its own.

There is no prompt, no temperature, no retry-with-different-output path anywhere in this
module.

## Tradeoffs

**What Organize provides:**

- Every `ClassifiedPage`, `SplitResult`, and `SectionResult` carries `ranges` pointing to
  exact Markdown offsets (`paperplane/contracts.py:70-78`), so readers can check the source
  text behind each result.
- When a rule finds no keyword or heading, Organize reports the partial result in `warnings`
  (`paperplane/ade_workflows.py:91-92` and `:109-112`).
- Organize makes no provider calls, adds no token cost or network latency, and does not need
  an API key. It runs on Parse output that already exists.

**What Organize does not provide:**

- **Classification quality is only as good as your class names.** As explained in
  [Tune Classify classes](../how-to/tune-classify-classes.md), the algorithm cannot
  understand semantics: `"invoice"` will not match a page whose text says "bill" unless you
  add that word yourself. A model-based classifier would generalize across synonyms and
  paraphrase without any tuning.
- **Section detection is shallow.** `section_document` only ever looks at the *first*
  grounded block of a page. It cannot detect a section that starts mid-page, and every
  detected section's `level` is hardcoded to `1`: there is no heading-depth inference
  (`paperplane/ade_workflows.py:32`, `:114-122`).
- **No cross-page semantic reasoning.** Classify and Section each look at one page at a
  time; they do not use the cross-page continuation logic that Parse itself applies (see
  `paperplane/document_intelligence.py`) to, for example, recognize that a section actually
  continues past a page break.

## Why Organize does not use a model

A model-based Organize workflow could match synonyms and detect section headings beyond the
first grounded block. Its results would be harder to verify against the source text: a model
could assign a label without a recoverable reason or paraphrase a section title. Organize
keeps its results repeatable and traceable to specific ranges by applying deterministic rules
to Parse output.

If you need semantic categorization that goes beyond keyword matching, the intended path is
to improve your `ClassDefinition` descriptions with the actual vocabulary your documents
use (see the how-to guide), not to expect Organize itself to infer meaning it was not built
to infer.
