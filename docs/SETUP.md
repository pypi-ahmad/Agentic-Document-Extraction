# Self-Hosted OCR Pipeline Setup Guide (GLM-OCR & PaddleOCR-VL-1.6)

Cross-platform setup for self-hosting the two vision-language OCR pipelines
this project can use as local, zero-API-cost engines:

- **GLM-OCR** ([zai-org/GLM-OCR](https://github.com/zai-org/GLM-OCR)) — a small
  (~0.5B decoder) VLM paired with PP-DocLayoutV3 for layout, served over an
  OpenAI-compatible chat-completions API.
- **PaddleOCR-VL-1.6** ([PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)) —
  PP-DocLayoutV3 layout + a 0.9B VLM, PaddlePaddle's own document pipeline.

Both are optional. Pick one (or both) based on what you want to compare or
which your hardware handles better. Every section below is GPU-first with an
explicit CPU fallback, across **Windows 11, macOS (Apple Silicon), Ubuntu,
and Fedora**.

> Every claim about platform support, package names, and CLI flags in this
> guide was checked against the projects' own docs/source/roadmaps at the
> time of writing (see [References](#references)) — not assumed. Where
> something couldn't be verified, it's called out explicitly rather than
> guessed.

---

## Table of contents

1. [Decision matrix — pick your path](#1-decision-matrix--pick-your-path)
2. [Prerequisites per OS](#2-prerequisites-per-os)
3. [GLM-OCR setup](#3-glm-ocr-setup)
4. [PaddleOCR-VL-1.6 setup](#4-paddleocr-vl-16-setup)
5. [Performance tuning](#5-performance-tuning)
6. [Connecting this repo to your server](#6-connecting-this-repo-to-your-server)
7. [Troubleshooting](#7-troubleshooting)
8. [References](#references)

---

## 1. Decision matrix — pick your path

Not every backend runs on every OS. This is the single most important thing
to get right before you start installing anything.

| Your OS | GPU backend for GLM-OCR | GPU backend for PaddleOCR-VL | CPU fallback |
|---|---|---|---|
| **Windows 11** | WSL2 (Ubuntu) + vLLM (recommended) or SGLang | WSL2 + official Docker `genai_server` (recommended) or native vLLM | WSL2 + vLLM CPU build |
| **Ubuntu 22.04/24.04** | vLLM (recommended) or SGLang | Docker `genai_server` (recommended) or native vLLM | vLLM CPU build / plain `paddlepaddle` |
| **Fedora 40+** | vLLM (recommended) or SGLang | Docker `genai_server` (recommended) or native vLLM | vLLM CPU build / plain `paddlepaddle` |
| **macOS (Apple Silicon)** | **mlx-vlm** (the only real GPU/Metal-accelerated path) | CPU only — **unverified**, see [§4.5](#45-macos-notes) | mlx-vlm already runs on the GPU via Metal; no separate CPU path needed |

Why it's laid out this way, confirmed from the projects' own sources:

- **vLLM has no native macOS GPU backend.** Apple Silicon GPU acceleration
  requires the separate, community-maintained **vLLM-Metal** plugin, not
  core vLLM. Core vLLM's macOS support is CPU-only (FP32/FP16, no
  prebuilt wheels — build from source).
  [[vLLM Apple GPU docs]](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/gpu.apple.inc.md)
  [[vLLM Apple CPU docs]](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/cpu.apple.inc.md)
- **SGLang has no macOS support at all** as of this writing — confirmed
  directly in the project's own roadmap issue ("SGLang has no support for
  Apple Silicon"). An MLX-based backend is work-in-progress, build-from-source
  only. SGLang's CPU backend is Intel-Xeon-AMX-only and covers text LLMs,
  not vision-language models — treat SGLang as **CUDA-only in practice** for
  this use case.
  [[SGLang roadmap issue]](https://github.com/sgl-project/sglang/issues/19137)
  [[SGLang CPU docs]](https://docs.sglang.io/platforms/cpu_server.html)
- **Neither vLLM nor SGLang has native Windows support.** WSL2 is the
  official, practical path on Windows for both.
- **PaddlePaddle's CPU inference is fully supported on x64**, but the
  project's own docs flag that general ARM CPU support is limited (only
  Huawei Ascend NPU images are called out) — Apple Silicon is ARM64, so
  treat the PaddleOCR-VL-on-Mac path as unverified; test with a small
  document before relying on it.
  [[PaddleOCR-VL docs]](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md)

---

## 2. Prerequisites per OS

### 2.1 Windows 11 (WSL2)

Open **PowerShell as Administrator**:

```powershell
wsl --install -d Ubuntu-24.04
# Restart if prompted
```

Install an up-to-date NVIDIA driver **on Windows itself** (Game Ready or
Studio driver — WSL2 GPU passthrough uses the Windows-side driver, you do
*not* install a separate Linux NVIDIA driver inside WSL2). Then, inside the
Ubuntu shell:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git curl
nvidia-smi   # should list your GPU if passthrough is working
```

From here, follow the **Ubuntu** instructions below inside your WSL2 shell —
everything is identical once you're in the Linux environment. `D:\...`
Windows paths are reachable from WSL2 at `/mnt/d/...`.

### 2.2 Ubuntu 22.04 / 24.04 (native or inside WSL2)

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3-pip python3-venv git curl
```

GPU driver: use Ubuntu's own driver manager or NVIDIA's `.run` installer per
your GPU generation — this is standard and not repeated here.

Install [`uv`](https://docs.astral.sh/uv/) (recommended over plain `pip`/`venv`):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2.3 Fedora 40+ (native)

NVIDIA driver setup on Fedora differs from Ubuntu — it goes through
**RPM Fusion**, not a `.run` installer:

```bash
sudo dnf update -y
sudo dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
  https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm
sudo dnf install -y akmod-nvidia xorg-x11-drv-nvidia-cuda
# wait ~5 minutes for the kernel module to build, then reboot
sudo reboot
```

After reboot, verify:

```bash
modinfo -F version nvidia
nvidia-smi
```

Then install base tooling:

```bash
sudo dnf install -y python3-pip git curl
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Source: [RPM Fusion NVIDIA how-to](https://rpmfusion.org/Howto/NVIDIA).

### 2.4 macOS (Apple Silicon)

```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python@3.12 git uv
```

There is no GPU driver step on macOS — Metal/unified memory is used
directly by MLX.

---

## 3. GLM-OCR setup

### 3.1 Linux / WSL2 (Windows, Ubuntu, Fedora) — common install

```bash
mkdir -p ~/GLM-OCR && cd ~/GLM-OCR   # or /mnt/d/AI/GLM-OCR on WSL2, your choice
uv venv --python 3.12
source .venv/bin/activate

uv pip install -U pip
uv pip install "transformers>=5.3.0"
uv pip install "glmocr[selfhosted]"
```

Pick **one** backend below (vLLM is the more mature/stable option; SGLang is
worth trying if you want to compare throughput on the same hardware).

#### Option A — vLLM (recommended)

```bash
uv pip install -U "vllm>=0.19.0"
```

Start the server:

```bash
vllm serve zai-org/GLM-OCR \
  --port 8080 \
  --served-model-name glm-ocr \
  --dtype auto \
  --gpu-memory-utilization 0.85 \
  --max-model-len 8192 \
  --allowed-local-media-path / \
  --speculative-config '{"method": "mtp", "num_speculative_tokens": 2}'
```

First run downloads the model (~2 GB). Keep this terminal open.

#### Option B — SGLang (alternative, often faster on supported hardware)

```bash
uv pip install "sglang>=0.5.10"

SGLANG_ENABLE_SPEC_V2=1 python -m sglang.launch_server \
  --model-path zai-org/GLM-OCR \
  --port 8080 \
  --served-model-name glm-ocr \
  --mem-fraction-static 0.85 \
  --context-len 8192 \
  --speculative-algorithm NEXTN \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4
```

### 3.2 CPU fallback (Linux/WSL2, no supported GPU)

vLLM ships a real CPU path for x86 Linux (no separate `vllm-cpu` PyPI
package — it's a build flag / dedicated wheel):

```bash
# Prebuilt CPU wheel (fastest to get running)
uv pip install "https://github.com/vllm-project/vllm/releases/download/v0.19.0/vllm-0.19.0+cpu-cp38-abi3-manylinux_2_34_x86_64.whl" --torch-backend cpu
# — or nightly —
uv pip install vllm --extra-index-url https://wheels.vllm.ai/nightly/cpu --index-strategy first-index --torch-backend cpu
```

Serve the same way as Option A, but drop GPU-specific flags
(`--gpu-memory-utilization`, `--speculative-config`) and expect
**significantly slower** inference — this is a functional fallback, not a
production-speed one. SGLang's CPU path is Xeon-AMX-only and doesn't cover
vision-language models, so it isn't a realistic CPU fallback for GLM-OCR —
use vLLM CPU instead.

Source: [vLLM x86 CPU install docs](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/cpu.x86.inc.md).

### 3.3 macOS notes

vLLM and SGLang don't run GLM-OCR on Apple Silicon GPUs (see
[§1](#1-decision-matrix--pick-your-path)). The real path is **mlx-vlm**, Apple's
MLX-based VLM server, with a community-converted GLM-OCR weight:

```bash
uv venv --python 3.12 ~/glmocr-mlx
source ~/glmocr-mlx/bin/activate

# GLM-OCR support needs the git version of mlx-vlm, not the latest PyPI release
uv pip install git+https://github.com/Blaizzy/mlx-vlm.git

mlx_vlm.server --model mlx-community/GLM-OCR-bf16 --port 8080
```

This exposes an OpenAI-compatible `/chat/completions` endpoint on port 8080,
same as vLLM/SGLang — everything downstream (the `glmocr` SDK's
`ocr_api.api_path`, and this repo's `glmocr_vlm_base_url` setting) points at
it identically. Use a **separate venv** from the `glmocr[selfhosted]` SDK
install — the two have conflicting `transformers` version requirements.

Sources: [mlx-vlm](https://github.com/Blaizzy/mlx-vlm),
[mlx-community/GLM-OCR-bf16](https://huggingface.co/mlx-community/GLM-OCR-bf16),
[GLM-OCR MLX deploy guide](https://github.com/zai-org/GLM-OCR/blob/main/examples/mlx-deploy/README.md).

### 3.4 Configure the official SDK (layout + OCR, full pipeline)

Create `config.yaml` (same on every OS — only the backend behind
`ocr_api` changes):

```yaml
pipeline:
  maas:
    enabled: false

  ocr_api:
    api_host: 127.0.0.1
    api_port: 8080
    model: glm-ocr           # or "GLM-OCR-bf16" style id if your mlx-vlm serve tag differs
    api_path: /v1/chat/completions
    api_mode: openai
    request_timeout: 300
    verify_ssl: false

  layout:
    model_dir: PaddlePaddle/PP-DocLayoutV3_safetensors
    threshold: 0.3
    batch_size: 1
    workers: 1
```

### 3.5 Run it

```bash
# CLI — layout on CPU keeps the GPU free for the VLM (recommended on 8GB cards)
glmocr parse your_document.pdf --layout-device cpu --config config.yaml --output ./output
```

```python
# Python
from glmocr import GlmOcr

with GlmOcr(config_path="config.yaml", layout_device="cpu") as parser:
    result = parser.parse("your_document.pdf")
    print(result.markdown_result)
    result.save("./output")
```

If you want to run the **full pipeline as a persistent HTTP service**
(what this repo's `GlmOcrLayoutEngine` talks to) instead of the CLI:

```bash
uv pip install "glmocr[server]"
python -m glmocr.server --config config.yaml
# now listening on :5002 — POST /glmocr/parse, GET /health
```

### 3.6 Optional helper scripts

```bash
# start_server.sh
#!/bin/bash
cd ~/GLM-OCR && source .venv/bin/activate
vllm serve zai-org/GLM-OCR --port 8080 --served-model-name glm-ocr \
  --dtype auto --gpu-memory-utilization 0.85 --max-model-len 8192 \
  --allowed-local-media-path / \
  --speculative-config '{"method": "mtp", "num_speculative_tokens": 2}'
```

```bash
# run_ocr.sh
#!/bin/bash
cd ~/GLM-OCR && source .venv/bin/activate
glmocr parse "$1" --layout-device cpu --config config.yaml --output ./output
```

```bash
chmod +x start_server.sh run_ocr.sh
```

---

## 4. PaddleOCR-VL-1.6 setup

### 4.1 Install (Linux / WSL2 — Windows, Ubuntu, Fedora)

```bash
uv venv --python 3.12 ~/PaddleOCR-VL
source ~/PaddleOCR-VL/bin/activate
uv pip install -U pip

# GPU build
uv pip install paddlepaddle-gpu==3.2.1 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
# — or CPU build, do NOT install both —
# uv pip install paddlepaddle==3.2.1

uv pip install -U "paddleocr[doc-parser]>=3.6.0"
```

GPU requirement per PaddlePaddle's own docs: compute capability ≥7.0 /
CUDA ≥11.8 for the PaddlePaddle/Transformers backend, ≥8.0 / CUDA ≥12.6
specifically for the vLLM backend below.

### 4.2 GPU backend — official Docker `genai_server` (recommended, most stable)

```bash
docker run --rm --gpus all --network host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu \
  paddleocr genai_server \
  --model_name PaddleOCR-VL-1.6-0.9B \
  --host 0.0.0.0 \
  --port 8080 \
  --backend vllm
```

### 4.3 GPU backend — native vLLM (alternative, no Docker)

```bash
vllm serve PaddlePaddle/PaddleOCR-VL-1.6 \
  --trust-remote-code \
  --served-model-name PaddleOCR-VL-1.6-0.9B \
  --max-num-batched-tokens 8192 \
  --gpu-memory-utilization 0.85 \
  --no-enable-prefix-caching \
  --mm-processor-cache-gb 0 \
  --port 8080
```

### 4.4 CPU fallback

```bash
uv pip install paddlepaddle==3.2.1   # instead of paddlepaddle-gpu
```

CPU inference is officially supported on x64. It will be **much slower**
than the GPU paths above (this is a functional fallback for machines
without a supported NVIDIA GPU, not a speed option) — no `vl_rec_backend
vllm-server` flag needed; the pipeline runs the VLM in-process on CPU.

### 4.5 macOS notes

Two real caveats, stated plainly rather than glossed over:

1. **No CUDA on macOS**, so the Docker/vLLM GPU paths above (§4.2, §4.3)
   don't apply at all.
2. **ARM CPU support is not general-purpose** per PaddleOCR's own docs —
   only Huawei Ascend NPU images are explicitly called out. Apple Silicon
   is ARM64. Whether `pip install paddlepaddle` actually produces a working
   macOS ARM64 wheel is **not verified** here — test it on your machine
   with a single small document before depending on this path. If it
   doesn't work, GLM-OCR via mlx-vlm (§3.3) is the reliable local-OCR
   option on Mac.

### 4.6 Run the pipeline

```bash
paddleocr doc_parser \
  -i your_document.pdf \
  --pipeline_version v1.6 \
  --vl_rec_backend vllm-server \
  --vl_rec_server_url http://127.0.0.1:8080/v1 \
  --save_path ./output
```

```python
from paddleocr import PaddleOCRVL

pipeline = PaddleOCRVL(
    pipeline_version="v1.6",
    vl_rec_backend="vllm-server",
    vl_rec_server_url="http://127.0.0.1:8080/v1",
)

output = pipeline.predict("your_document.pdf")
for res in output:
    res.print()
    res.save_to_markdown(save_path="./output")
    res.save_to_json(save_path="./output")
```

For CPU-fallback mode, drop `vl_rec_backend`/`vl_rec_server_url` entirely —
the pipeline runs everything in-process.

### 4.7 Optional helper scripts

```bash
# start_server.sh
#!/bin/bash
docker run --rm --gpus all --network host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-genai-vllm-server:latest-nvidia-gpu \
  paddleocr genai_server --model_name PaddleOCR-VL-1.6-0.9B \
  --host 0.0.0.0 --port 8080 --backend vllm
```

```bash
# run_ocr.sh
#!/bin/bash
cd ~/PaddleOCR-VL && source bin/activate
paddleocr doc_parser -i "$1" --pipeline_version v1.6 \
  --vl_rec_backend vllm-server --vl_rec_server_url http://127.0.0.1:8080/v1 \
  --save_path ./output
```

---

## 5. Performance tuning

General guidance, scaled to whatever VRAM you have rather than one fixed
card:

| Setting | Recommended value | Reason |
|---|---|---|
| Layout device | `cpu` | Frees VRAM entirely for the VLM — layout detection is cheap on CPU |
| `gpu-memory-utilization` / `mem-fraction-static` | 0.80–0.85 on 8GB cards; can push to 0.90+ on 16GB+ | Leaves headroom to avoid OOM under load |
| `max-model-len` / `--context-len` | 8192 | Covers most documents; raise only if you hit truncation |
| Speculative decoding (MTP for vLLM, NEXTN for SGLang) | Enabled | Real speed boost, low risk |
| Concurrent requests | 1–4 on 8GB cards; scale up with more VRAM | Avoid OOM from batched KV cache growth |

Rough accuracy/speed ranking across the options in this guide, GPU tier
held constant:

1. **Official pipeline (PP-DocLayoutV3 + VLM) + vLLM/SGLang backend** —
   best accuracy, fastest practical speed. Recommended default.
2. **Official pipeline + Docker `genai_server`** — same accuracy, slightly
   more overhead than native vLLM, most dependency-free/stable to set up.
3. **CPU fallback (any backend)** — same accuracy, much slower. Use when
   no supported GPU is available.
4. **mlx-vlm on Apple Silicon** — accuracy comparable to the GPU paths
   above (same underlying weights), genuinely GPU-accelerated via Metal,
   not a "worse" tier — just the correct-and-only path on Mac.

---

## 6. Connecting this repo to your server

Once either server is running and reachable, this repository's backend
picks it up through `backend/app/config.py` settings (defaults already
match the ports used throughout this guide):

```bash
# .env (backend)
GLMOCR_SERVER_URL=http://localhost:5002   # glmocr[server] full pipeline (layout engine)
GLMOCR_VLM_BASE_URL=http://localhost:8080/v1   # raw vLLM/SGLang/mlx-vlm chat-completions endpoint (zone repair)
```

- `GLMOCR_SERVER_URL` is used by `GlmOcrLayoutEngine`
  (`backend/app/services/parsing/glmocr_layout_engine.py`) for initial page
  segmentation — needs `glmocr[server]` running (§3.5).
- `GLMOCR_VLM_BASE_URL` is used by the `"glmocr"` vision provider
  (`backend/app/services/parsing/vision_providers.py`) for targeted
  per-region repair — needs just the raw vLLM/SGLang/mlx-vlm server (§3.1–3.3),
  the `glmocr[server]` wrapper is not required for this path.
- Set `ocr_provider: "glmocr"` (already this app's default) in a parse
  request to route zone-repair through it.

If you're running the server inside WSL2 and the backend on Windows,
WSL2's default networking shares `localhost` with the Windows host — no
extra port-forwarding should be needed. Verify with `curl localhost:5002/health`
and `curl localhost:8080/v1/models` from Windows before assuming it's wired
correctly.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `nvidia-smi` not found inside WSL2 | Driver only installed inside WSL2, not on Windows | Install the NVIDIA driver on **Windows**, not inside the WSL2 shell — WSL2 GPU passthrough uses the Windows driver |
| vLLM/SGLang OOM on startup | `gpu-memory-utilization`/`mem-fraction-static` too high for your VRAM | Lower to 0.7–0.8, or reduce `--max-model-len`/`--context-len` |
| `glmocr` import errors mentioning `transformers` version conflicts | Same venv used for both `glmocr[selfhosted]` and `mlx-vlm` | Use separate virtual environments (§3.3) |
| First request to vLLM/SGLang times out | Model still downloading (~2GB for GLM-OCR) | Wait for the download to finish before sending requests; check the server's own log output |
| PaddleOCR-VL fails to install/run on Apple Silicon | ARM64 wheel support is not guaranteed (§4.5) | Fall back to GLM-OCR via mlx-vlm for local OCR on Mac |
| `curl localhost:5002/health` fails from Windows when server runs in WSL2 | WSL2 networking mode (mirrored vs. NAT) doesn't share `localhost` in your setup | Check `wsl.exe --status` for networking mode, or bind the server to `0.0.0.0` and use the WSL2 VM's IP (`ip addr` inside WSL2) instead of `localhost` |

---

## References

- GLM-OCR — [GitHub](https://github.com/zai-org/GLM-OCR), [Hugging Face model card](https://huggingface.co/zai-org/GLM-OCR)
- vLLM — [Apple GPU (Metal plugin) docs](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/gpu.apple.inc.md), [Apple CPU docs](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/cpu.apple.inc.md), [x86 CPU docs](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/cpu.x86.inc.md), [vLLM-Metal plugin](https://github.com/vllm-project/vllm-metal)
- SGLang — [Apple Silicon roadmap issue](https://github.com/sgl-project/sglang/issues/19137), [CPU server docs](https://docs.sglang.io/platforms/cpu_server.html)
- mlx-vlm — [GitHub](https://github.com/Blaizzy/mlx-vlm), [mlx-community/GLM-OCR-bf16](https://huggingface.co/mlx-community/GLM-OCR-bf16), [GLM-OCR MLX deploy example](https://github.com/zai-org/GLM-OCR/blob/main/examples/mlx-deploy/README.md)
- PaddleOCR-VL — [pipeline docs](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/pipeline_usage/PaddleOCR-VL.en.md), [PaddlePaddle install](https://www.paddlepaddle.org.cn/en/install/quick)
- RPM Fusion NVIDIA how-to (Fedora) — [rpmfusion.org/Howto/NVIDIA](https://rpmfusion.org/Howto/NVIDIA)
- This repo's integration — `backend/app/services/parsing/glmocr_layout_engine.py`, `backend/app/services/parsing/vision_providers.py`, `backend/app/config.py`
