# Run Paperplane

## One-click Windows launch

Double-click `Paperplane.cmd`. It verifies `workspace_app.py`, `pyproject.toml`, and
`uv.lock`; installs uv, Python 3.12.10, and LibreOffice when needed; selects CUDA 13.0 or
CPU; and checks the locked environment and required Docling/RapidOCR and PP-DocLayoutV3
model files. It synchronizes dependencies or downloads models only when they are missing
or out of date.
Otherwise it launches the multipage app directly at `http://127.0.0.1:8551`.

Close the launcher window or press Ctrl+C to stop it.
Each launcher start clears Streamlit's data cache. Each **Parse files** action also clears
the previous batch from every output tab before processing begins.
On Windows, starting the launcher again safely stops an existing Paperplane process on port
`8551` before setup. If another application owns that port, the launcher leaves it running
and reports the conflict. Paperplane starts Streamlit through its platform runner, which uses
the Windows Selector event loop to avoid harmless Proactor `WinError 10054` disconnect
tracebacks when browser connections reset.

## Stop from the UI

Select **Stop and clear** in the sidebar from any page, then confirm. Paperplane clears its
Streamlit data/resource caches and active session, blanks all Paperplane tabs in the same
browser, stops the backend with a successful exit, and closes the launcher. Downloaded
models, seven-day job history, and saved job artifacts are preserved. If browser JavaScript
is disabled, the backend still stops and open tabs show as disconnected.

## One-file Linux launch

Run `./Paperplane.sh` from the repository. It performs the same repository, Python,
dependency, model, and provider-key checks as the Windows launcher. Ubuntu/Debian users can
allow it to install missing LibreOffice through APT; other distributions must provide
LibreOffice first. Open `http://127.0.0.1:8551` and press Ctrl+C to stop the app.

## Manual launch

```powershell
uv python install 3.12.10
uv sync --locked --extra cpu
uv run --locked --extra cpu python -m paperplane.streamlit_runner run workspace_app.py --server.port=8551
```

For Ollama ADE, start Ollama first and optionally set
`OLLAMA_BASE_URL=http://127.0.0.1:11434`. Cloud credentials are read from the current
process environment, Windows user environment, an ignored `.env`, or Streamlit secrets.
Gemini uses `GOOGLE_API_KEY`; legacy `GEMINI_API_KEY` is checked only when the canonical
variable is absent.
Agnes 2.5 Flash accepts selected page images inline for Parse and cloud enhancement.
GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR are automatically run on PP-DocLayoutV3 page
regions with their native prompts. DeepSeek retries one empty or transiently failed text
crop before skipping it with a visible warning.

The pages are Parse, Organize, Jobs, and Benchmarks. Select one Parse engine before
uploading. Parse controls remain in the sidebar; the full-width canvas shares one document
selector across Input preview, Output, Annotated PDF, Markdown, HTML, and JSON. Download one
selected document at a time or the whole result batch as a ZIP. Job metadata and artifacts
are private to `%LOCALAPPDATA%\Paperplane` and expire after seven days.
