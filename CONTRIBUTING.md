# Contributing

Read the [README](README.md), [architecture](docs/ARCHITECTURE.md), and
[development guide](docs/DEVELOPMENT.md) first.

## Ground rules

- Keep Paperplane local, Streamlit-only, and stateless.
- Make one focused change per pull request.
- Use conventional commit subjects.
- Add tests for observable behavior changes.
- Never commit API keys, `.streamlit/secrets.toml`, uploads, or results.
- Update affected documentation in the same change.

## Local setup

```powershell
uv python install 3.12.10
uv sync --locked --extra test --extra lint --extra docs
```

Before opening a pull request:

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

Report security issues privately as described in [SECURITY.md](SECURITY.md).
