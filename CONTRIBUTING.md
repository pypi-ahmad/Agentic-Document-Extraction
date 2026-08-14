# Contributing

Read the [README](README.md), [architecture](docs/ARCHITECTURE.md), and
[development guide](docs/DEVELOPMENT.md) first.

## Ground rules

- Keep Paperplane local, Streamlit-only, and stateless.
- Make one focused change per pull request.
- Use conventional commit subjects.
- Add tests for observable behavior changes.
- Never commit API keys, `.streamlit/secrets.toml`, uploads, or results.
- Preserve both provider paths: OpenAI uses `OPENAI_API_KEY` and optional
  `OPENAI_BASE_URL`; Agnes 2.5 Flash uses `AGNES_API_KEY`.
- Update affected documentation in the same change.

## Local setup

```powershell
uv python install 3.12.10
uv sync --locked --extra test --extra lint --extra docs
uv run streamlit run streamlit_app.py --server.port=8551
```

Before opening a pull request:

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
```

Report security issues privately as described in [SECURITY.md](SECURITY.md).
