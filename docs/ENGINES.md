# Processing engines

All four engine toggles are off initially. Activating one turns the others off. Paperplane
never auto-routes a batch.

| Engine | Input | Primary work | Cloud key |
|---|---|---|---|
| Docling ADE | PDF, images, modern Office/OpenDocument/CSV | Local layout, tables, OCR, reading order | No |
| PDF Inspector ADE | PDF only | Local PDF inspection, Markdown, positioned text, OCR flags | No |
| Cloud AI ADE | All supported inputs | Sends every selected visual page to the chosen provider | Yes |
| Ollama ADE | All supported inputs | Local layout detection plus installed Ollama vision OCR | No |

The **Enhance with cloud AI** option runs after Docling, PDF Inspector, or Ollama. The
selected cloud model and its credential are then required. Agnes receives private visual
inputs inline, like the other cloud models.

Ollama defaults to `http://127.0.0.1:11434`. Every installed model is visible, but Parse is
disabled unless `/api/show` reports `vision`. `glm-ocr:latest` and
`AuditAid/PaddleOCR-VL-1.6-0.9B:latest` are calibration targets, not a fixed allowlist.
For GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR, PP-DocLayoutV3 first detects regions locally
on CPU. Ollama recognizes the resulting crops with family-specific native prompts instead
of being forced to emit a whole-page JSON schema.

DeepSeek-OCR retries an empty text crop once with a stricter transcription prompt. It also
retries transient transport, malformed-response, HTTP 408/429, and server failures once
after 500 ms. One exhausted crop becomes a page warning while successful sibling regions
remain; three consecutive exhausted regions stop the page. Other OCR profiles retain their
existing behavior.

Local semantic workflows use the shared contracts and return deterministic partials with
warnings when evidence is insufficient. They never silently invoke another engine.
