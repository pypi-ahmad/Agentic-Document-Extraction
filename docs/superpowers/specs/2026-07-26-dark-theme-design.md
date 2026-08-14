# Archived design: dark theme

## Status

Superseded by Paperplane's Streamlit UI on 2026-08-14.

## Historical design

The former design specified a React-controlled theme toggle, pre-hydration script,
`localStorage` preference, CSS variables, and light/dark component testing. That frontend
was removed in v4.

## Current design

The checked-in `.streamlit/config.toml` supplies one red-and-black dark theme with explicit
primary, surface, text, border, and control-radius values. Streamlit owns rendering and
interaction; there is no custom theme persistence or client-side script.

Any future theme selection must use supported Streamlit behavior, remain accessible, and
avoid reintroducing a JavaScript application solely for presentation.
