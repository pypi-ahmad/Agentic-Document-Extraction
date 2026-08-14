# Qoder project context

Paperplane 5.0.0 is a Python 3.12/Streamlit application inspired by LandingAI ADE. Launch
`workspace_app.py`; `streamlit_app.py` is only the Parse page.

Four engine toggles are exclusive and initially off: Docling, PDF Inspector, Cloud AI,
Ollama. Cloud enhancement can follow a local engine. Files are parallel but isolated;
cross-page context is limited to selected pages in one file.

Parse configuration lives below navigation in the sidebar. The main canvas uses one shared
document selector and full-width Input preview, Output, Annotated PDF, Markdown, HTML, and
JSON tabs. Individual downloads follow the selected document; the batch ZIP contains every
successful document's available outputs and a versioned status manifest, never source uploads.

Public outputs are strict ADE v2-style Parse JSON and namespaced Paperplane v5 JSON.
Classify/Split/Section require citations or explicit partial warnings.
Word boxes must come from native PDF/RapidOCR observations. Calibration requires an exact
engine/model/version/corpus profile.

SQLite job metadata and private artifacts are stored under `%LOCALAPPDATA%\Paperplane` for
seven days. There is no HTTP API, JavaScript frontend, authentication, or hosted profile.

Run:

```powershell
uv run --extra cpu streamlit run workspace_app.py --server.port=8551
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
```

Never expose secrets, fabricate evidence/scores, or restore removed service/frontend stacks.
