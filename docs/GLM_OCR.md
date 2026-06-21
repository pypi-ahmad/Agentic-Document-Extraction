# GLM-OCR (local Ollama) — setup and contract

> How the GLM-OCR engine plugs into the parser layer of Agentic
> Document Extraction.

---

## 1. What GLM-OCR is

GLM-OCR is a multimodal OCR model from Zhipu AI / THUDM. Unlike
traditional text-detection OCR (PaddleOCR, Tesseract), it is a small
**vision-language model** that reads the whole page at once and
returns the recognized text, implicitly aware of layout, headings,
and tables.

In this project it is exposed as a user-selectable parser engine
(`glmocr`) that runs entirely against a local **Ollama** server. No
API key, no cloud spend, no telemetry leaves the host.

| Property          | Value                                                                |
| ----------------- | -------------------------------------------------------------------- |
| Model size        | ~1.1 B parameters                                                     |
| Context length    | 131 072 tokens                                                        |
| Vision encoder    | Custom ViT, 336 px image size, 14×14 patches                         |
| Input formats     | PNG, JPEG, TIFF                                                       |
| Output            | Plain text (with layout/markdown noise filtered by the adapter)       |
| Inference         | Local — Ollama server, default `http://localhost:11434`               |

---

## 2. When to use it

Use GLM-OCR when:

- you want a vision-language OCR engine that understands layout
  context (multi-column invoices, mixed-size headings, table grids);
- you cannot or will not send document images to a third-party API;
- you can run an Ollama server with a GPU on the same host (or are
  willing to accept CPU latency for small batches).

Use PyMuPDF instead when you have text-based PDFs (it is faster and
needs no model).

Use PaddleOCR instead when you have a CPU-only machine and the docs
are simple receipts / forms without complex layout.

---

## 3. Install and configure

### 3.1 Install Ollama and pull the model

```bash
# Linux / macOS
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &              # if not already running as a service
ollama pull glm-ocr:latest
```

Confirm the model is local:

```bash
ollama list            # glm-ocr:latest should appear
curl -s localhost:11434/api/tags | jq '.models[].name' | grep glm-ocr
```

### 3.2 Configure the backend

Edit `backend/.env` (or copy `backend/.env.example` first):

```bash
ENABLE_GLM_OCR=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_GLM_OCR_MODEL=glm-ocr:latest
GLM_OCR_TIMEOUT_SECONDS=120
```

Restart the backend. Confirm it is wired:

```bash
curl -s localhost:8000/api/providers/parsers | jq
# Expect a "glmocr" entry with available=true and enabled=true.
```

### 3.3 Use it

- In the frontend, pick **GLM-OCR (local Ollama)** in the parser
  dropdown for an image upload, or leave it on **Auto** and let the
  router pick it.
- In the API, set `ocr_provider: "glmocr"` (or `"auto"`) in the
  `POST /api/extractions/` body.

---

## 4. The contract this adapter exposes

`app/services/ocr/glm_ocr_provider.py` is the only file that talks
to Ollama. It conforms to the standard `BaseOCRProvider` contract
(`app/services/ocr/base.py`):

| Method / property       | Behaviour                                                                              |
| ----------------------- | -------------------------------------------------------------------------------------- |
| `provider_id`           | `"glmocr"`                                                                              |
| `display_name`          | `"GLM-OCR (local Ollama)"`                                                              |
| `feature_flag_name`     | `"enable_glm_ocr"`                                                                      |
| `supported_file_types`  | `{"png", "jpeg", "tiff"}`                                                               |
| `is_user_selectable`    | `True`                                                                                  |
| `is_available()`        | GETs `/api/tags`; returns `True` only if the configured model is pulled.                |
| `extract_text(path)`    | Reads the file, base64-encodes it, POSTs `/api/generate` with `stream=false`.            |
| Output                  | An `OCRResult` with cleaned text, a single page, and `raw.engine == "glm-ocr"`.        |

The output text is post-processed to remove:

- HTML comments (`<!-- ... -->`)
- layout HTML tags (`<table>`, `<tr>`, `</invoice>`, etc.)
- empty markdown code-fence lines (`\`\`\``)
- empty single-tag lines
- duplicate block transcriptions (GLM-OCR sometimes echoes the
  same text twice)

This is the same work the rest of the pipeline expects from any
OCR engine: clean natural-language text, no markup, no commentary.

---

## 5. Failure modes

| Symptom                                                    | Cause                                                   | Fix                                                                  |
| ---------------------------------------------------------- | ------------------------------------------------------- | -------------------------------------------------------------------- |
| `available=false` in `/api/providers/parsers`              | Model not pulled, or `OLLAMA_BASE_URL` unreachable.     | `ollama pull glm-ocr:latest`; check `curl localhost:11434/api/tags`.   |
| 500 with `Could not reach local Ollama at …`               | Server is down or behind a different port.              | Set `OLLAMA_BASE_URL`; restart the backend.                          |
| HTTP 503 from Ollama                                       | Ollama is busy or out of memory.                         | Wait, or raise `OLLAMA_NUM_PARALLEL` / `OLLAMA_MAX_LOADED_MODELS`.   |
| Empty `response` field from Ollama                         | Image is blank or model can't decode it.                 | Re-render the page at higher resolution; try a different OCR engine.  |
| `eval_count: 0` and only layout tokens returned            | Prompt was misconfigured.                                | You overrode the prompt; revert to the default.                       |

---

## 6. Performance notes

- A single image OCR call with GLM-OCR on a modern CPU takes
  roughly 1–5 s. On a GPU, sub-second.
- The model loads once per request by default; if you run a tight
  loop, keep the Ollama server warm and consider bumping
  `OLLAMA_KEEP_ALIVE`.
- For long documents, render each page to a separate image and
  call the engine once per page; the current adapter treats each
  upload as a single page.

---

## 7. Tests

The provider has a focused unit test under
`backend/tests/test_glm_ocr_provider.py` that exercises:

- layout-markup stripping;
- HTML comment removal;
- empty-fence stripping;
- metadata (provider id, display name, supported types, PDF
  rejection);
- availability probe across success, missing model, connection
  error, and non-200 status;
- feature-flag handling (`enable_glm_ocr=false` disables routing);
- `extract_text` happy path with a mocked Ollama response;
- `extract_text` empty-response path.

Run it with:

```bash
pytest backend/tests/test_glm_ocr_provider.py -v
```
