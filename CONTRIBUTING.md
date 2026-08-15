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

Report security issues privately as described in [SECURITY.md](SECURITY.md).
