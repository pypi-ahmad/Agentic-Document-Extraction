# Contributing

Contributions are welcome. Fork or clone the repository, make one focused change, and open
a pull request. By submitting a contribution, you agree that it may be distributed under
Paperplane's [MIT License](LICENSE). No contributor license agreement or DCO sign-off is
required.

Read the [README](README.md), [architecture](docs/ARCHITECTURE.md), and
[development guide](docs/DEVELOPMENT.md) first.

## Ground rules

- Keep Paperplane local, Streamlit-only, and stateless.
- Make one focused change per pull request.
- Use conventional commit subjects.
- Add tests for observable behavior changes.
- Never commit API keys, `.streamlit/secrets.toml`, user uploads, or private results.
- Use synthetic, redacted, or clearly redistributable fixtures. You are responsible for
  ensuring that any submitted data may legally and safely be published.
- Preserve all catalog entries and their provider-specific credentials documented in
  `docs/MODELS.md`; `OPENAI_BASE_URL` remains an optional OpenAI-only override.
- Update affected documentation in the same change.

## Local setup

```powershell
uv python install 3.12.10
uv sync --locked --extra cpu --extra test --extra lint --extra docs
uv run --extra cpu streamlit run workspace_app.py --server.port=8551
```

Before opening a pull request:

```powershell
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run ruff format --check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
```

## Manual smoke test

For user-visible changes, also run the app with a synthetic, redacted, or redistributable
document:

1. Start `Paperplane.cmd` on Windows or `./Paperplane.sh` on Linux.
2. Select the affected engine and model, then parse only the pages needed for the test.
3. Check Input preview, Output, Annotated PDF, Markdown, HTML, and JSON as applicable.
4. Change between Parse, Organize, Jobs, and Cost and confirm relevant session data remains.
5. Confirm errors are actionable and no credential value or private document content appears
   in the UI, terminal, saved fixture, screenshot, or test output.

Describe the manual scenario and result in the pull request. A change that does not affect
the UI or parsing workflow may state that the smoke test was not applicable.

## Reporting bugs and requesting features

Use the [bug report form](https://github.com/pypi-ahmad/Agentic-Document-Extraction/issues/new?template=bug_report.yml)
for reproducible failures and the
[feature request form](https://github.com/pypi-ahmad/Agentic-Document-Extraction/issues/new?template=feature_request.yml)
for proposed behavior. Search existing issues first. Reports should identify the version,
operating system, engine, model, selected pages, expected behavior, actual behavior, and
sanitized logs when relevant.

Read [SUPPORT.md](SUPPORT.md) for community support and [DISCLAIMER.md](DISCLAIMER.md) for
the responsibility attached to files, credentials, providers, costs, and generated output.

Report security issues privately as described in [SECURITY.md](SECURITY.md).
