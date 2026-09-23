---
type: Operations
title: Setup, model storage, and shutdown
description: How the Windows and Linux launchers prepare Paperplane, where managed model weights live, and what Stop and clear preserves.
tags: [setup, operations, models, shutdown]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-33d83ea58a9d8da61b254adf
    resource: repo://Paperplane.cmd
  - id: openwiki-source-2730258e37f39e7b07bee6d3
    resource: repo://Paperplane.sh
  - id: openwiki-source-51f4b0c13b8275f810db149b
    resource: repo://paperplane/model_store.py
  - id: openwiki-source-262fdcf12bf066c90575bf3b
    resource: repo://paperplane/shutdown.py
  - id: openwiki-source-b17edb32932079667d5313ca
    resource: repo://paperplane/streamlit_runner.py
  - id: openwiki-source-05ccef8d4cf1698187f20464
    resource: repo://pyproject.toml
  - id: openwiki-source-30007c902df0a151cd03e9b3
    resource: repo://workspace_app.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Setup, model storage, and shutdown

Paperplane supports Python 3.12 and uses `uv.lock` to keep its runtime dependencies pinned. The Windows and Linux launchers install or locate `uv`, install LibreOffice when needed, prepare the locked environment, check the permanent model set, and start the Streamlit workspace on `127.0.0.1:8551`.

## Start the app

On Windows, run `Paperplane.cmd` from the checkout. It can install `uv` and LibreOffice, selects the CPU or `cu130` PyTorch extra, and retries with CPU if CUDA dependency setup fails. Before setup, it stops a previous Paperplane launcher tree on port 8551; an unrelated process using that port blocks startup.

On Ubuntu or Debian, run `./Paperplane.sh`. It can install `uv` and uses APT, with `sudo` when needed, to install LibreOffice. It selects `cu130` when `nvidia-smi` succeeds and falls back to CPU if CUDA dependency setup fails. On distributions without APT, install LibreOffice using the distribution's package manager first.

Both launchers use Python 3.12.10, synchronize from the lock file, validate Torch and Docling imports, prepare the model store, clear Streamlit's cache, and launch the app. A CUDA-capable Torch runtime is exercised with a small convolution when CUDA reports as available; this is a startup check, not a guarantee that every workload fits the device.

For manual setup, install Python 3.12.10, run `uv sync --locked` with the needed extras, prepare the model store with `python -m paperplane.model_store --prepare`, then start `workspace_app.py` through Streamlit on port 8551. The project supports Python `>=3.12,<3.13`; the launchers pin the patch version to 3.12.10.

## Permanent model weights

Paperplane's managed Docling, RapidOCR, and PP-DocLayoutV3 weights live outside the checkout in a versioned user-data directory:

- Windows: `%LOCALAPPDATA%\Paperplane\models\sets\v1`
- Linux: `${XDG_DATA_HOME:-~/.local/share}/Paperplane/models/sets/v1`

The model store checks its versioned manifest, recorded file sizes, and required model files. When the set is incomplete, it first copies compatible files from the legacy Docling cache and a locally available layout-model snapshot; if needed, it downloads missing weights and writes a new manifest. This storage is separate from the repository and virtual environment, so removing those does not remove the managed weights. Ollama models remain managed by Ollama.

## Stop and clear

The sidebar's **Stop and clear** action asks for confirmation, clears Streamlit data and resource caches plus the current session state, tells other open Paperplane tabs to leave the UI, and schedules the process to exit. Downloaded models, job history, and saved artifacts are preserved.

## Related pages

- [Quickstart and navigation](../quickstart.md)
- [Paperplane system overview](../architecture/system-overview.md)
- [Local job storage and lifecycle](../architecture/job-storage-and-lifecycle.md)
- [Provider catalog and cost reporting](../integrations/provider-catalog-and-cost.md)
