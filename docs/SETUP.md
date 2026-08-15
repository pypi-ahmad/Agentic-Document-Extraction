# Setup

## Automatic Windows setup

1. Clone or download the complete repository.
2. Double-click `Paperplane.cmd`.
3. Let the first dependency and model downloads complete if they are needed.

The launcher is the single setup/start file. It installs missing uv, Python 3.12.10,
LibreOffice, locked CPU/CUDA dependencies in copy mode so uv works quietly across different
Windows drives, and the permanent Docling/RapidOCR/PP-DocLayoutV3 model set, then runs
`workspace_app.py` on port `8551`. Existing weights are copied from their old caches without
network access. On later runs it validates the manifest and sizes, skips downloads, and
launches the app directly. Node.js, Docker,
and a C++ compiler are not required. Python-Markdown and Bleach are runtime dependencies for
sanitized standalone HTML output and are installed through the same locked environment.
Before launch, Paperplane imports Torch, Transformers, and Docling to verify that binary
dependencies are complete; it automatically reinstalls Torch and Torchvision if that health
check fails. Starting a new launcher stops any earlier Paperplane launcher tree before
dependency checks, preventing an older app from restarting and locking `.venv` DLLs during
repair.

## Automatic Linux setup

From a cloned checkout on Ubuntu or Debian:

```bash
./Paperplane.sh
```

If needed, restore execute permission with `chmod +x Paperplane.sh`. The launcher installs
missing uv and Python in the current user's environment, uses APT and sudo only when
LibreOffice is absent, selects CUDA when `nvidia-smi` succeeds, falls back to CPU when
necessary, synchronizes the locked environment, prepares the permanent model set, and
starts the same localhost app. On non-APT distributions,
install LibreOffice with the distribution's package manager before running the launcher.

## Manual developer setup

```powershell
uv python install 3.12.10
uv sync --locked --extra cpu --extra test --extra lint --extra docs
uv run --locked --extra cpu python -m paperplane.model_store --prepare
uv run --locked --extra cpu streamlit run workspace_app.py --server.port=8551
```

The versioned model set lives at `%LOCALAPPDATA%\Paperplane\models\sets\v1` on Windows
and `${XDG_DATA_HOME:-~/.local/share}/Paperplane/models/sets/v1` on Linux. Do not delete
that directory unless the weights should be removed. Repository and `.venv` cleanup do not
affect it. New pinned model-set versions are installed alongside older sets. Ollama models
are managed separately by Ollama.

Use `--extra cu130` instead of `--extra cpu` on a compatible NVIDIA system.
The Windows launcher removes external CUDA Toolkit directories from Paperplane's child
process `PATH`, allowing the cu130 PyTorch wheel to use its matching bundled cuDNN libraries.
It verifies Torch package metadata and a CUDA convolution before launch, repairing Torch when
that probe fails. Synchronization is inexact so separately installed test, lint, and docs
extras are not removed.

## Credentials and Ollama

Set only the provider variables you use: `OPENAI_API_KEY`, `OPENAI_BASE_URL`,
`XAI_API_KEY`, `GOOGLE_API_KEY`, `ANTHROPIC_API_KEY`, or `AGNES_API_KEY`. Paperplane also
accepts `OLLAMA_BASE_URL`, defaulting to `http://127.0.0.1:11434`.

Each operator supplies and secures their own provider credentials and is responsible for
the associated provider terms, data handling, and charges. Local Docling, PDF Inspector,
and loopback Ollama use do not require a cloud API key.

Gemini uses `GOOGLE_API_KEY`. Existing `GEMINI_API_KEY` configurations remain a fallback
only when the canonical variable is absent. On Windows, `Paperplane.cmd` refreshes both
values from the current user's environment before launch; `GOOGLE_API_KEY` wins when both
exist. The launcher confirms credential availability without printing its value. An ignored
`.env` and Streamlit secrets use the same names.

`AGNES_API_KEY` enables both text and private visual workflows. Paperplane sends selected
page PNGs inline, so no public image host is required.

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "your-key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_BASE_URL", "https://api.openai.com", "User")
[Environment]::SetEnvironmentVariable("GOOGLE_API_KEY", "your-key", "User")
```

Linux shells can export the variables before launch:

```bash
export OPENAI_API_KEY="your-key"
./Paperplane.sh
```

Open a new terminal after changing a Windows user variable. Other users can copy
`.env.example` to the ignored `.env`. Never commit secrets. Install and start Ollama
separately for Ollama ADE; Paperplane discovers installed models and checks vision support.
