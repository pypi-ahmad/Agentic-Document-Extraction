# Archived design: Evidence Studio

## Status

Superseded by Paperplane's Streamlit workspace on 2026-08-14.

## Historical design

The design described a multi-pane React dashboard with run history, API-backed job state,
artifact fetching, evaluation, cancellation, and browser object-URL management. Those
services and frontend components were removed in v4.

## Current design

The current workspace is intentionally direct:

```text
preview document | configure and parse
                 | inspect Output / Annotated PDF / Markdown / JSON
                 | download PDF / Markdown / JSON
```

Only the current upload and result live in Streamlit session state. Failures remain
actionable: parse errors are shown safely, annotated-PDF failure is isolated, and semantic
Office evidence is clearly distinguished from physical source overlays.

Future workspace changes should improve this flow without adding saved run history,
polling, or persistence unless the product boundary is explicitly revised.
