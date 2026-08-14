# Archived plan: Evidence Studio

## Status

Superseded by the Streamlit-only Paperplane architecture; reviewed for v5.0.0 on 2026-08-14. The former
Next.js job dashboard and API polling components no longer exist.

## Original intent

The plan proposed a document-first workspace with source preview, run navigation, result
inspection, artifact preview, evaluation, responsive layouts, and a Graphite Signal visual
system.

## Current v5.0.0 result

Paperplane keeps the useful document-first workflow without the removed service stack:

- one upload and preview area;
- four explicit engines plus six-model cloud selection and installed Ollama discovery;
- Fast, Balanced, and Audit mode selection;
- direct in-process parsing;
- Output, Annotated PDF, Markdown, and JSON tabs;
- annotated PDF, Markdown, strict ADE v2 JSON, and Paperplane JSON downloads;
- Extract and Organize workflow pages; and
- seven-day local SQLite job/artifact history with cancellation state and deletion.

The entrypoint is `workspace_app.py`; Parse remains in `streamlit_app.py` and its workflow is covered by
`tests/test_streamlit_app.py`.

## Future change boundary

Workspace improvements must preserve the single-process, local-only boundary and bounded
seven-day retention unless a separate product decision explicitly changes it.
