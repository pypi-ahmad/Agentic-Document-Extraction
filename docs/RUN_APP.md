# Run Paperplane


> **V2 status (2026-08-14):** The active runtime is OpenAI-only and uses versioned recipes, bounded Terra verification, safe partial results, and private evidence bundles. This page retains older detail where useful; [README](../README.md) and [V2 architecture](ARCHITECTURE_V2.md) are authoritative for current behavior.

## PowerShell — prerequisite checks

```powershell
git --version
uv --version
node --version
npm --version
docker version
nvidia-smi
```

## Bash — prerequisite checks

```bash
git --version
uv --version
node --version
npm --version
docker version
nvidia-smi
```

## PowerShell — optional Ollama prerequisite check

```powershell
ollama --version
```

## Bash — optional Ollama prerequisite check

```bash
ollama --version
```

## PowerShell — first-time setup

```powershell
git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction.git
Set-Location Agentic-Document-Extraction
uv python install 3.12.10
uv sync --locked
if (-not (Test-Path .env)) { Copy-Item backend/.env.example .env }
New-Item -ItemType Directory -Force .cache\paddleocr-vl
```

## Bash — first-time setup

```bash
git clone https://github.com/pypi-ahmad/Agentic-Document-Extraction.git
cd Agentic-Document-Extraction
uv python install 3.12.10
uv sync --locked
test -e .env || cp backend/.env.example .env
mkdir -p .cache/paddleocr-vl
```

## PowerShell — verify Docker GPU and pull PaddleOCR-VL 1.6

```powershell
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
docker pull ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu@sha256:ad0b1f056a76967f9191cd06398e8babb21b49a4673a28c3de5fd31f481884db
docker image inspect ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu@sha256:ad0b1f056a76967f9191cd06398e8babb21b49a4673a28c3de5fd31f481884db
```

## Bash — verify Docker GPU and pull PaddleOCR-VL 1.6

```bash
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
docker pull ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu@sha256:ad0b1f056a76967f9191cd06398e8babb21b49a4673a28c3de5fd31f481884db
docker image inspect ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu@sha256:ad0b1f056a76967f9191cd06398e8babb21b49a4673a28c3de5fd31f481884db
```

## PowerShell — Terminal 1 — start optional Ollama server if none is running

```powershell
ollama serve
```

## PowerShell — Terminal 2 — pull optional models after Ollama is ready

```powershell
ollama pull glm-ocr:latest
ollama pull qwen3.5:9b
ollama list
```

## Bash — Terminal 1 — start optional Ollama server if none is running

```bash
ollama serve
```

## Bash — Terminal 2 — pull optional models after Ollama is ready

```bash
ollama pull glm-ocr:latest
ollama pull qwen3.5:9b
ollama list
```

## PowerShell — Terminal 3 — start backend from repository root

```powershell
uv run uvicorn app.main:app `
  --app-dir backend `
  --reload `
  --reload-dir backend `
  --host 127.0.0.1 `
  --port 8000
```

## Bash — Terminal 3 — start backend from repository root

```bash
uv run uvicorn app.main:app \
  --app-dir backend \
  --reload \
  --reload-dir backend \
  --host 127.0.0.1 \
  --port 8000
```

## PowerShell — Terminal 4 — start frontend from repository root

```powershell
Set-Location frontend
npm ci
npm run dev
```

## Bash — Terminal 4 — start frontend from repository root

```bash
cd frontend
npm ci
npm run dev
```

## PowerShell — verify services

```powershell
curl.exe --fail-with-body http://127.0.0.1:8000/health
curl.exe --fail-with-body http://127.0.0.1:8000/health/ready
curl.exe --fail-with-body http://127.0.0.1:8000/info
curl.exe --fail-with-body http://127.0.0.1:3000
Start-Process "http://localhost:3000"
Start-Process "http://localhost:8000/docs"
```

## Bash — verify services

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail-with-body http://127.0.0.1:8000/health/ready
curl --fail http://127.0.0.1:8000/info
curl --fail http://127.0.0.1:3000
uv run python -m webbrowser http://localhost:3000
uv run python -m webbrowser http://localhost:8000/docs
```

## PowerShell — parse a document from repository root on the selected backend port

```powershell
$BackendOrigin = "http://127.0.0.1:8000"
$job = curl.exe --fail-with-body -X POST "$BackendOrigin/api/parse-jobs" `
  -F "file=@Sample-PDF/PublicWaterMassMailing.pdf" `
  -F 'settings={"input_mode":"mixed","processing_mode":"local_only","dpi":200,"marginalia_policy":"remove_repeated","describe_figures":true,"searchable_pdf":true,"bundle":true}' | ConvertFrom-Json
$jobId = $job.id
do {
  Start-Sleep -Seconds 2
  $job = Invoke-RestMethod "$BackendOrigin/api/parse-jobs/$jobId"
  $job.status
} while ($job.status -notin @("completed", "completed_with_warnings", "failed", "cancelled", "paused"))
if ($job.status -notin @("completed", "completed_with_warnings")) { throw "Parse job ended with status $($job.status)" }
$bundle = $job.artifacts | Where-Object type -eq "bundle" | Select-Object -First 1
if (-not $bundle) { throw "Completed job did not produce a bundle" }
Invoke-WebRequest ($BackendOrigin + $bundle.download_url) -OutFile "$jobId.zip"
```

## Bash — parse a document from repository root on the selected backend port

```bash
backend_origin=http://127.0.0.1:8000
job_json=$(curl --fail-with-body -X POST "$backend_origin/api/parse-jobs" \
  -F 'file=@Sample-PDF/PublicWaterMassMailing.pdf' \
  -F 'settings={"input_mode":"mixed","processing_mode":"local_only","dpi":200,"marginalia_policy":"remove_repeated","describe_figures":true,"searchable_pdf":true,"bundle":true}')
job_id=$(printf '%s' "$job_json" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
while true; do
  sleep 2
  job_json=$(curl --fail-with-body "$backend_origin/api/parse-jobs/$job_id")
  status=$(printf '%s' "$job_json" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  printf '%s\n' "$status"
  case "$status" in
    completed|completed_with_warnings) break ;;
    failed|cancelled|paused) exit 1 ;;
  esac
done
bundle_url=$(printf '%s' "$job_json" | uv run python -c 'import json,sys; a=next((x for x in json.load(sys.stdin)["artifacts"] if x["type"]=="bundle"), None); print(a["download_url"] if a else "")')
test -n "$bundle_url"
curl --fail-with-body "$backend_origin$bundle_url" --output "$job_id.zip"
```

## PowerShell — Terminal 3 — backend on port 8001 from repository root

```powershell
uv run uvicorn app.main:app --app-dir backend --reload --reload-dir backend --host 127.0.0.1 --port 8001
```

## PowerShell — Terminal 4 — frontend for backend port 8001 from repository root

```powershell
$env:PAPERPLANE_BACKEND_ORIGIN = "http://127.0.0.1:8001"
Set-Location frontend
npm ci
npm run dev
```

## PowerShell — verify port 8001

```powershell
curl.exe --fail-with-body http://127.0.0.1:8001/health
curl.exe --fail-with-body http://127.0.0.1:8001/health/ready
curl.exe --fail-with-body http://127.0.0.1:8001/info
curl.exe --fail-with-body http://127.0.0.1:3000
Start-Process "http://localhost:3000"
Start-Process "http://localhost:8001/docs"
```

## Bash — Terminal 3 — backend on port 8001 from repository root

```bash
uv run uvicorn app.main:app --app-dir backend --reload --reload-dir backend --host 127.0.0.1 --port 8001
```

## Bash — Terminal 4 — frontend for backend port 8001 from repository root

```bash
export PAPERPLANE_BACKEND_ORIGIN=http://127.0.0.1:8001
cd frontend
npm ci
npm run dev
```

## Bash — verify port 8001

```bash
curl --fail http://127.0.0.1:8001/health
curl --fail-with-body http://127.0.0.1:8001/health/ready
curl --fail http://127.0.0.1:8001/info
curl --fail http://127.0.0.1:3000
uv run python -m webbrowser http://localhost:3000
uv run python -m webbrowser http://localhost:8001/docs
```

## PowerShell — production frontend from repository root

```powershell
Set-Location frontend
npm ci
npm run build
npm run start
```

## Bash — production frontend from repository root

```bash
cd frontend
npm ci
npm run build
npm run start
```

## PowerShell — optional Ollama container from repository root

```powershell
docker compose up -d ollama
docker compose logs -f ollama
```

## Bash — optional Ollama container from repository root

```bash
docker compose up -d ollama
docker compose logs -f ollama
```

## PowerShell — stop each foreground Ollama, backend, and frontend terminal

```powershell
Ctrl+C
```

## PowerShell — stop optional Ollama container from repository root

```powershell
docker compose down
```

## Bash — stop each foreground Ollama, backend, and frontend terminal

```bash
Ctrl+C
```

## Bash — stop optional Ollama container from repository root

```bash
docker compose down
```
