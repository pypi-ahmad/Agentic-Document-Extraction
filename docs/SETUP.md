# Setup

## Automatic Windows setup

1. Clone or download the complete repository.
2. Double-click `Paperplane.cmd`.
3. Let the first dependency and model downloads complete if they are needed.

The launcher is the single setup/start file. It installs missing uv, Python 3.12.10,
LibreOffice, locked CPU/CUDA dependencies in copy mode so uv works quietly across different
Windows drives, and Docling/RapidOCR models, then runs
`workspace_app.py` on port `8551`. On later runs it checks the locked environment and model
artifacts, skips setup when they are ready, and launches the app directly. Node.js, Docker,
and a C++ compiler are not required. Python-Markdown and Bleach are runtime dependencies for
sanitized standalone HTML output and are installed through the same locked environment.
Before launch, Paperplane imports Torch and Docling to verify that binary dependencies are
complete; it automatically reinstalls Torch and Torchvision if that health check fails.

## Automatic Linux setup

From a cloned checkout on Ubuntu or Debian:

```bash
./Paperplane.sh
```

If needed, restore execute permission with `chmod +x Paperplane.sh`. The launcher installs
missing uv and Python in the current user's environment, uses APT and sudo only when
LibreOffice is absent, selects CUDA when `nvidia-smi` succeeds, falls back to CPU when
necessary, synchronizes the locked environment, downloads missing Docling/RapidOCR models,
and starts the same localhost app. On non-APT distributions, install LibreOffice with the
distribution's package manager before running the launcher.

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

`AGNES_API_KEY` enables both text and private visual workflows. Paperplane sends selected
page PNGs inline, so no public image host is required.

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
```

Linux shells can export the variables before launch:

```bash
export OPENAI_API_KEY="your-key"
./Paperplane.sh
```

Open a new terminal after changing a Windows user variable. Other users can copy
`.env.example` to the ignored `.env`. Never commit secrets. Install and start Ollama
separately for Ollama ADE; Paperplane discovers installed models and checks vision support.
