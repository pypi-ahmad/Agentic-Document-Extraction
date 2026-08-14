# Quality and verification

Paperplane combines model output with deterministic validation. It does not treat a model
response as trusted merely because it matches a JSON shape.

## Extraction safeguards

- strict structured-output schemas for OpenAI calls
- bounded reasoning, reconciliation, crop verification, and repair policies
- native-word alignment when selectable PDF text exists
- normalized coordinate validation and crop-to-page transforms
- duplicate suppression and stable reading-order reconciliation
- critical-token preservation checks
- non-empty fallback behavior when optional verification fails
- exact Markdown range and hierarchy validation
- table-cell nesting and span metadata validation
- automatic per-page native/scanned routing
- explicit grounded versus semantic-only geometry
- figure placeholders and warnings when descriptions are unavailable

## UI and artifact safeguards

- allowlist sanitization before model-produced HTML is rendered
- XSRF protection and localhost-only binding
- isolated annotated-PDF failures that do not erase successful parses
- source overlays for physical evidence
- semantic reports instead of invented Office coordinates
- safe user-facing errors without provider payload or secret disclosure

## Automated coverage

The test suite covers document validation, configuration precedence, OpenAI request
construction, geometry, pipeline decisions, reconciliation, contracts, runtime composition,
Docling routing, annotated PDFs, and the Streamlit workflow. AppTest exercises all four
lazy result views and all three downloads.

Repository checks:

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

These checks validate implementation contracts. They are not a production accuracy
benchmark or a claim of LandingAI ADE parity. High-impact extracted values always require
human review against source evidence.
