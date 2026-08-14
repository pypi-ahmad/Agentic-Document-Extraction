# Setup

## Automatic Windows setup

1. Clone or download the complete repository.
2. Double-click `Paperplane.cmd`.
3. Let the first dependency and model downloads complete if they are needed.

The launcher is the single setup/start file. It installs missing uv, Python 3.12.10,
LibreOffice, locked CPU/CUDA dependencies, and Docling/RapidOCR models, then runs
`workspace_app.py` on port `8551`. On later runs it checks the locked environment and model
artifacts, skips setup when they are ready, and launches the app directly. Node.js, Docker,
and a C++ compiler are not required. Python-Markdown and Bleach are runtime dependencies for
sanitized standalone HTML output and are installed through the same locked environment.

## Manual developer setup

```powershell
uv python install 3.12.10
uv sync --locked --extra cpu --extra test --extra lint --extra docs
uv run --locked --extra cpu docling-tools models download layout tableformer rapidocr --quiet
uv run --locked --extra cpu streamlit run workspace_app.py --server.port=8551
```

Use `--extra cu130` instead of `--extra cpu` on a compatible NVIDIA system.

## Credentials and Ollama

Set only the provider variables you use: `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
`XAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or `AGNES_API_KEY`. Paperplane also
accepts `OLLAMA_BASE_URL`, defaulting to `http://127.0.0.1:11434`.

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
```

Open a new terminal after changing a Windows user variable. Other users can copy
`.env.example` to the ignored `.env`. Never commit secrets. Install and start Ollama
separately for Ollama ADE; Paperplane discovers installed models and checks vision support.
