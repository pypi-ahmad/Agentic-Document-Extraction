# Local runbook

## App does not start

Confirm `workspace_app.py`, `pyproject.toml`, and `uv.lock` exist, then run:

```powershell
uv --version
uv sync --locked --extra cpu
uv run --extra cpu streamlit run workspace_app.py --server.port=8551
```

## Engine cannot start

- Cloud: set the selected model's key and reopen the terminal.
- Ollama: start Ollama, verify `OLLAMA_BASE_URL`, and choose a model reporting `vision`.
- Agnes: set `AGNES_API_KEY`; private visual inputs are sent inline.
- PDF Inspector: use PDF input only.
- Office: rerun `Paperplane.cmd` on Windows or `Paperplane.sh` on Linux. Linux automatic
  LibreOffice installation requires APT; otherwise install it with the distribution's
  package manager.

For GLM-OCR, PaddleOCR-VL, or DeepSeek-OCR detector errors, verify or repair the local
layout model:

```powershell
uv run --locked --extra cpu python -m paperplane.ollama_ocr --check
uv run --locked --extra cpu python -m paperplane.model_store --prepare
```

The repair command validates the complete permanent model set and downloads only missing or
incomplete pinned files. It does not modify models managed by Ollama.

Use `--extra cu130` instead of `--extra cpu` when that is the synchronized environment.

If Docling reports `CUDNN_STATUS_SUBLIBRARY_VERSION_MISMATCH`, restart through the current
Windows launcher. It isolates PyTorch's bundled CUDA runtime from system CUDA Toolkit DLLs
and validates a CUDA convolution before starting. A missing Torch `RECORD` file now fails the
same health probe and triggers the existing targeted Torch/torchvision reinstall while the
previous Paperplane process is stopped.

DeepSeek automatically retries one empty or transiently failed region. A completed parse
may show `DeepSeek OCR skipped ... after two attempts`; inspect that page for missing text.
`DeepSeek OCR stopped after three consecutive region failures` indicates sustained local
model/server trouble: confirm Ollama is responsive, confirm the selected model remains
loaded, and retry the page.

## Parsing or artifact generation fails

Check file integrity, page range, the 20-file/1-GiB batch limit, 200-MiB/500-page file
limit, provider access, and terminal logs. One file or annotated-PDF failure does not erase
other successful batch results. Provider errors are sanitized.

If an individual download is missing, confirm that the selected document completed and
that its annotated PDF was generated. The whole-batch ZIP still includes all other
available outputs; inspect `manifest.json` for per-document and artifact errors. Source
uploads are intentionally absent from the ZIP.

## Job recovery and cleanup

Open **Jobs** to inspect pending/running/completed/failed/cancelled state. Checkpoints and
artifacts live under `%LOCALAPPDATA%\Paperplane`. Delete one job or use **Clear all**.
Expired data is purged after seven days. A stopped Streamlit process does no compute; run it
again before resuming work.

## Cost differs from an invoice

The UI multiplies provider-reported tokens by configured synchronous base rates. Gemini
3.7 uses $0.75/$3.75 per million input/output tokens through December 31, 2026; Luna cache
reads use $0.02/1M. It does not infer Batch discounts, taxes, Grok long-context/fast
surcharges, or account entitlements.

## Verify the checkout

```powershell
uv run ruff check paperplane app_pages tests streamlit_app.py workspace_app.py scripts
uv run pyright
uv run pytest -q
uv run python scripts/benchmark_report.py
uv run streamlit run workspace_app.py --server.port=8551
```
