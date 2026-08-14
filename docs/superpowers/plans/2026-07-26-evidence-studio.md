# Archived plan: Evidence Studio

## Status

Superseded by the Streamlit-only Paperplane v4 architecture on 2026-08-14. The former
Next.js job dashboard, API polling, cancellation, run history, and artifact components no
longer exist.

## Original intent

The plan proposed a document-first workspace with source preview, run navigation, result
inspection, artifact preview, evaluation, responsive layouts, and a Graphite Signal visual
system.

## Current v4.1 result

Paperplane keeps the useful document-first workflow without the removed service stack:

- one upload and preview area;
- OpenAI or Agnes 2.5 Flash model selection;
- Fast, Balanced, and Audit mode selection;
- direct in-process parsing;
- Output, Annotated PDF, Markdown, and JSON tabs;
- annotated PDF, Markdown, and JSON downloads; and
- one session-local result with no run history, polling, cancellation, or evaluation store.

The current implementation is `streamlit_app.py`; its public workflow is covered by
`tests/test_streamlit_app.py`.

## Future change boundary

Workspace improvements must preserve the single-process, database-free, session-only
contract unless a separate product decision explicitly changes it.
