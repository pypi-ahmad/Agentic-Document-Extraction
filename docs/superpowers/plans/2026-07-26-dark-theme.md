# Archived plan: dark theme

## Status

Superseded by the Streamlit-only Paperplane v4 architecture on 2026-08-14. Do not execute
the former Next.js/React implementation steps; those files and dependencies were removed.

## Original intent

The plan proposed a dark default, an accessible light/dark toggle, persisted browser
preference, and semantic color tokens for the former Next.js interface.

## Current v4.2 result

- Streamlit is the only UI runtime.
- `.streamlit/config.toml` defines the checked-in dark visual theme.
- The application does not add custom JavaScript, browser storage, or a theme toggle.
- Native Streamlit widgets preserve keyboard and accessibility behavior.
- UI verification lives in `tests/test_streamlit_app.py` plus manual browser inspection.

## Future change boundary

A theme selector should use supported Streamlit capabilities, preserve the localhost and
session-only model, add AppTest coverage, and avoid reintroducing React or client-side state
frameworks. A new approved plan is required before implementation.
