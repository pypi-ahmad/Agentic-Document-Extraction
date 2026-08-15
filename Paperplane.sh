#!/usr/bin/env bash

set -Eeuo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"

fail() {
    printf '\nERROR: %s\n' "$1" >&2
    exit 1
}

printf '\n========================================\n'
printf '  Paperplane launcher\n'
printf '========================================\n\n'

for required_file in pyproject.toml uv.lock workspace_app.py; do
    [[ -f "$required_file" ]] || fail "$required_file was not found next to Paperplane.sh."
done

find_uv() {
    if command -v uv >/dev/null 2>&1; then
        command -v uv
        return
    fi
    for candidate in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [[ -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return
        fi
    done
    return 1
}

uv_exe="$(find_uv || true)"
if [[ -z "$uv_exe" ]]; then
    printf 'Installing uv because it is not available...\n'
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | sh
    else
        fail "Install curl or wget, then run Paperplane.sh again."
    fi
    uv_exe="$(find_uv || true)"
fi
[[ -n "$uv_exe" ]] || fail "uv could not be installed automatically."
printf 'uv is ready.\n'

find_soffice() {
    if command -v soffice >/dev/null 2>&1; then
        command -v soffice
        return
    fi
    if command -v libreoffice >/dev/null 2>&1; then
        command -v libreoffice
        return
    fi
    return 1
}

soffice_exe="$(find_soffice || true)"
if [[ -z "$soffice_exe" ]]; then
    if ! command -v apt-get >/dev/null 2>&1; then
        fail "LibreOffice is required. Install it with your distribution's package manager, then run Paperplane.sh again."
    fi
    printf 'Installing LibreOffice because it is not available...\n'
    if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
        apt-get update
        apt-get install -y libreoffice
    elif command -v sudo >/dev/null 2>&1; then
        sudo apt-get update
        sudo apt-get install -y libreoffice
    else
        fail "LibreOffice installation requires root access or sudo."
    fi
    soffice_exe="$(find_soffice || true)"
fi
[[ -n "$soffice_exe" ]] || fail "LibreOffice was installed but soffice could not be located."
printf 'LibreOffice is ready.\n'

torch_extra="cpu"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    torch_extra="cu130"
fi

venv_python="$script_dir/.venv/bin/python"
venv_docling="$script_dir/.venv/bin/docling-tools"

printf 'Checking the locked Python environment...\n'
dependencies_ready=""
if "$uv_exe" sync --check --locked --python 3.12.10 --extra "$torch_extra" >/dev/null 2>&1; then
    dependencies_ready=1
elif [[ "$torch_extra" == "cu130" ]] \
    && "$uv_exe" sync --check --locked --python 3.12.10 --extra cpu >/dev/null 2>&1; then
    torch_extra="cpu"
    dependencies_ready=1
fi

if [[ -z "$dependencies_ready" ]]; then
    printf 'Python or locked dependencies are missing or out of date.\n'
    if ! "$uv_exe" python find 3.12.10 >/dev/null 2>&1; then
        printf 'Installing Python 3.12.10...\n'
        "$uv_exe" python install 3.12.10
    fi

    printf 'Synchronizing locked dependencies with the %s PyTorch backend...\n' "$torch_extra"
    if ! "$uv_exe" sync --locked --python 3.12.10 --extra "$torch_extra" --link-mode copy; then
        if [[ "$torch_extra" != "cu130" ]]; then
            fail "Locked dependency synchronization failed."
        fi
        printf 'CUDA dependency setup failed. Retrying with the CPU backend...\n'
        torch_extra="cpu"
        "$uv_exe" sync --locked --python 3.12.10 --extra cpu --link-mode copy \
            || fail "Locked CPU dependency synchronization failed."
    fi
fi

[[ -x "$venv_python" ]] || fail "The locked environment does not contain Python."
[[ -x "$venv_docling" ]] || fail "The locked environment does not contain docling-tools."
if ! "$venv_python" -c \
    "import torch.backends; from docling.datamodel.base_models import DocumentStream; from transformers import AutoModelForObjectDetection" \
    >/dev/null 2>&1; then
    printf 'The Torch or Docling installation is incomplete. Repairing it...\n'
    "$uv_exe" sync --locked --python 3.12.10 --extra "$torch_extra" --link-mode copy \
        --reinstall-package torch --reinstall-package torchvision \
        || fail "Torch and Docling repair failed."
    "$venv_python" -c \
        "import torch.backends; from docling.datamodel.base_models import DocumentStream; from transformers import AutoModelForObjectDetection" \
        >/dev/null 2>&1 || fail "Torch or Docling remains unusable after repair."
fi
printf 'Locked Python environment is ready.\n'

cache_root="${DOCLING_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/docling}"
model_root="$cache_root/models"
model_files=(
    "docling-project--docling-layout-heron/model.safetensors"
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tableformer_accurate.safetensors"
    "docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json"
    "RapidOcr/PP-OCRv6_det_small.pth"
    "RapidOcr/PP-OCRv6_rec_small.pth"
    "RapidOcr/ch_ptocr_mobile_v2.0_cls_mobile.pth"
    "RapidOcr/PP-OCRv6_det_small.onnx"
    "RapidOcr/PP-OCRv6_rec_small.onnx"
    "RapidOcr/ch_ppocr_mobile_v2.0_cls_mobile.onnx"
    "RapidOcr/ppocrv6_dict.txt"
)

models_ready=1
for model_file in "${model_files[@]}"; do
    if [[ ! -f "$model_root/$model_file" ]]; then
        models_ready=""
        break
    fi
done

if [[ -z "$models_ready" ]]; then
    printf 'Downloading local layout, table, and OCR models because they are not available...\n'
    "$venv_docling" models download layout tableformer rapidocr --quiet \
        || fail "Local document model download failed."
fi

printf 'Local document models are ready.\n'
if ! "$venv_python" -m paperplane.ollama_ocr --check >/dev/null 2>&1; then
    printf 'Downloading PP-DocLayoutV3 for Ollama OCR region detection...\n'
    "$venv_python" -m paperplane.ollama_ocr --download \
        || fail "Ollama OCR layout model download failed."
fi
printf 'Ollama OCR layout model is ready.\n'
printf 'Clearing previous Streamlit cache...\n'
"$venv_python" -m streamlit cache clear >/dev/null \
    || fail "Streamlit cache cleanup failed."
printf 'Starting Paperplane...\n'
printf 'Open http://127.0.0.1:8551 in your browser.\n'
printf 'Press Ctrl+C to stop the app.\n\n'

if [[ -z "${OPENAI_API_KEY:-}" \
    && -z "${XAI_API_KEY:-}" \
    && -z "${GOOGLE_API_KEY:-}" \
    && -z "${GEMINI_API_KEY:-}" \
    && -z "${ANTHROPIC_API_KEY:-}" \
    && -z "${AGNES_API_KEY:-}" ]]; then
    printf 'Note: No supported model API key is set in this shell.\n'
    printf 'Cloud AI and cloud enhancement require the key for the selected model.\n'
    printf 'Docling, PDF Inspector, and a running local Ollama can work without a cloud key.\n\n'
fi

exec "$venv_python" -m paperplane.streamlit_runner run workspace_app.py --server.port=8551
