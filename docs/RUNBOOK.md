# Local runbook

## App does not start

Confirm the repository contains `pyproject.toml`, `uv.lock`, and `streamlit_app.py`. Then:

```powershell
uv --version
uv sync --locked
uv run streamlit run streamlit_app.py --server.port=8551
```

If `uv` is missing, run `Paperplane.cmd` again with internet access so WinGet or the official
installer can complete.

## A scan or image asks for an API key

Set the environment variable listed for the selected model in [MODELS.md](MODELS.md).
Select the matching model in the UI. Alternatively use ignored `.env` or Streamlit secrets.
Native PDFs and supported Office files do not require a key.

## Provider request fails

Check the selected model's credential, provider network access, account model access, and
local terminal logs. For OpenAI only, also check `OPENAI_BASE_URL` and Responses API
compatibility. Paperplane displays a safe summary instead of raw provider payloads. The
default request timeout is 180 seconds.

## File is rejected

Check the extension, integrity, 200 MB limit, 500-page/frame limit, PDF canvas size, and
decoded image size. Legacy Office formats, RTF, encrypted PDFs, and password-protected
documents are unsupported.

## Local model setup fails

Check internet access and free disk space, then run:

```powershell
uv run docling-tools models download layout tableformer --quiet
```

Restart Paperplane after the download succeeds. Torch compilation is intentionally disabled
for the Windows layout path; Visual Studio build tools are not required.

## Annotated PDF is unavailable

The Markdown and JSON parse can still be valid because evidence-PDF generation is isolated.
Review the UI error and terminal log, then inspect the JSON grounding directly. Office
sources normally receive a semantic evidence report instead of source-page overlays.

## Clear local state

Choose **New extraction**, select another file, close the browser tab, or stop Streamlit.
This releases the upload, result, and generated annotated PDF from session state.

## Verification

```powershell
uv run ruff check paperplane tests streamlit_app.py scripts
uv run ruff format --check paperplane tests streamlit_app.py scripts
uv run pyright
uv run pytest tests -q
uv run streamlit run streamlit_app.py --server.port=8551
```
