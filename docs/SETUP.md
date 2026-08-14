# Setup

## Automatic Windows setup

1. Download or clone the complete repository.
2. Double-click `Paperplane.cmd`.
3. Allow first-time runtime, dependency, and model downloads to finish.

The launcher installs `uv`, Python 3.12.10, exact locked dependencies, and Docling layout
and table models. Windows 11 and internet access are the only initial setup requirements.
No Node.js, container runtime, GPU, C++ compiler, database, or local model server is needed.

## Credentials

An OpenAI key is required for scans and images and enables native-document figure
descriptions. Native PDFs and supported Office files can run locally without it.

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
```

Open a new terminal after setting user variables. Configuration precedence is:

1. existing process or Windows user environment;
2. ignored `.env` copied from `.env.example`;
3. ignored `.streamlit/secrets.toml` copied from its example; and
4. the built-in `https://api.openai.com` base URL.

Never place a real key in an example file or commit it.

## Manual runtime setup

```powershell
uv python install 3.12.10
uv sync --locked
uv run docling-tools models download layout tableformer --quiet
uv run streamlit run streamlit_app.py
```

## Development extras

```powershell
uv sync --locked --extra test --extra lint --extra docs
```

See [RUN_APP.md](RUN_APP.md) for normal operation and [DEVELOPMENT.md](DEVELOPMENT.md) for
the contributor workflow.
