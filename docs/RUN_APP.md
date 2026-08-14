# Run Paperplane

## One-click Windows launch

Double-click `Paperplane.cmd`. It:

1. verifies it is beside `pyproject.toml`, `uv.lock`, and `streamlit_app.py`;
2. installs `uv` with WinGet or the official installer when missing;
3. installs Python 3.12.10;
4. creates or updates `.venv` from `uv.lock`;
5. downloads Docling layout and table models; and
6. starts the local Streamlit app.

The first run needs internet access. Later runs reuse installed tools and model weights
while still checking the locked dependency set.

## Credentials

The launcher refreshes `OPENAI_API_KEY` and `OPENAI_BASE_URL` from the current Windows
user's environment registry. It never prints or writes their values.

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
```

Open a new terminal after changing a user variable. If user-level variables are unavailable,
copy `.env.example` to `.env` or `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml`. Both destination files are ignored by Git.

Without a key, native PDFs and supported Office files remain available. Scans and images
show an actionable error, and native-document figures use explicit placeholders.

## Terminal launch

```powershell
uv sync --locked
uv run --locked streamlit run streamlit_app.py
```

The checked-in configuration binds to `127.0.0.1`, enables XSRF protection, and caps
uploads at 200 MB.

## Use and stop

After parsing, inspect Output, Annotated PDF, Markdown, and JSON. Downloading the annotated
PDF, Markdown, or JSON is the only application-supported persistence action.

Choose **New extraction** to clear the workspace. Press Ctrl+C or close the launcher window
to stop Streamlit and end active sessions.
