# Engines

This document is the v0.4.0 reference for the OCR / parser
engines that ship with the app, the VLM-as-extractor path,
the engine deprecation policy, and the per-engine
recommendations (when to use which, what they cost).

## OCR / parser engines

| Engine     | Type           | Best for                                         | Default |
| ---------- | -------------- | ------------------------------------------------ | ------- |
| `pymupdf`  | built-in       | text-native PDFs (no install, no ML)             | yes     |
| `paddleocr` | 2.x / 3.x     | scanned images, receipts                         | opt-in  |
| `glmocr`   | local Ollama   | scanned forms, stamps, handwritten fields        | opt-in  |
| `docling`  | IBM ML parser  | PDFs / DOCX / PPTX with tables and multi-column  | opt-in  |

### `pymupdf` (built-in)

- **Cost**: zero (no install, no ML weights).
- **Latency**: < 100 ms per page.
- **Limitations**: only works on text-native PDFs. Scanned
  PDFs return an empty page. Image uploads are not supported.
- **When to use**: text-native PDFs (the most common case for
  invoices, contracts, reports). Auto routing picks it
  automatically when the PDF has extractable text.

### `paddleocr` (opt-in, `ENABLE_PADDLEOCR=true`)

- **Cost**: ~250 MB disk (PaddleOCR 3.x) + the model
  weights.
- **Latency**: ~1 s per image.
- **Limitations**: image-only (PNG, JPEG, TIFF). No layout
  understanding, no table extraction.
- **When to use**: receipt and document scanning on simple
  single-page images. Auto routing uses it for images when
  GLM-OCR is not available.
- **Version note**: v0.4.0 added the PaddleOCR 3.x
  `predict()` API. The 2.x `ocr()` API is still supported
  via `PADDLEOCR_USE_V2=1` for users on legacy installs.

### `glmocr` (opt-in, `ENABLE_GLM_OCR=true`)

- **Cost**: requires the `glm-ocr:latest` Ollama model
  (~3 GB) running locally.
- **Latency**: ~3 s per image (vision model).
- **Strengths**: handles forms, stamps, handwritten fields,
  and noisy backgrounds better than PaddleOCR.
- **When to use**: the default image OCR engine when
  available. Recommended for invoices with stamps and
  signatures.

### `docling` (opt-in, `ENABLE_DOCLING=true`)

- **Cost**: ~1.5 GB model weights (downloaded on first
  run to `~/.cache/docling/`).
- **Latency**: 5-15 s per page, but produces structured
  Markdown that downstream LLMs can parse reliably.
- **Strengths**: layout analysis, table extraction, mixed
  text + figures. Handles PDF, DOCX, PPTX, XLSX, images,
  HTML. The best choice for multi-page reports.
- **When to use**: any document with tables, multi-column
  layouts, or a mix of figures and text. The triage node
  (Commit 11) routes PDFs to Docling by default when
  Docling is available.

## VLM-as-extractor (`ENABLE_VLM_EXTRACT=true`)

A separate, parallel path: the document image is sent
directly to a vision-language model (PaddleOCR-VL-1.6 or
any Ollama-served VLM like `glm-ocr:latest` in chat mode),
which produces the structured JSON in one shot.

| VLM backend  | Install                | Latency   |
| ------------ | ---------------------- | --------- |
| `ollama`     | `ollama serve` + model | ~3-5 s    |
| `paddleocr-vl` | `pip install paddleocr-vl>=1.6` | ~5-10 s |

**Trade-offs**:

- Wins on tables, complex layouts, scanned forms (one
  call instead of OCR + LLM).
- Slower on simple receipts (overkill).
- 5-20x more expensive than the OCR + small-LLM path.
- Cap at 1-4 pages of context (most VLMs).

Recommended use: `extractor=vlm` opt-in per request, with
the G-Eval judge (Commit 6) confirming the VLM path is
worth the cost.

## Engine deprecation policy

- **No silent deprecations.** When an engine is removed or
  its feature flag is renamed, a release note ships in
  the same minor release and the engine stays on disk
  with a `DeprecationWarning` for at least one minor
  release cycle.
- **Default engines never disappear without a major
  release.** Engines that are on by default
  (`pymupdf` in v0.4.0) require a major version bump
  to be removed.
- **Backwards compatibility shims.** PaddleOCR 2.x
  (`PADDLEOCR_USE_V2=1`) ships as a legacy escape hatch
  through the next minor release. The shim itself is
  documented and tested.
- **Engine list exposure.** The
  `GET /api/providers/parsers` endpoint is the single
  source of truth: clients should never hard-code engine
  IDs. New engines appear in the response automatically
  when their feature flag is flipped.

## Adding a new engine

1. Subclass `BaseOCRProvider` in
   `backend/app/services/ocr/`.
2. Add the engine to
   `app.services.ocr.registry._PROVIDER_CLASSES` and to
   `AUTO_PRIORITY` if appropriate.
3. Add the feature flag to `Settings` (default `False`).
4. Add the engine to `ParserEngine` enum if user-visible.
5. Add tests in `backend/tests/test_<engine>_provider.py`.
6. Document in this file.

## Routing decision (the triage node)

The v0.4.0 `triage` node (in front of `parse`) records
the routing decision for observability:

| File type | Recommended engine         | Reason                              |
| --------- | -------------------------- | ----------------------------------- |
| `.pdf`    | `docling`                  | layout + tables                     |
| `.png/.jpg/.jpeg/.tiff/.tif/.bmp/.webp` | `glmocr`  | vision model, forms + stamps        |
| `.docx/.pptx/.xlsx` | `docling`         | structured documents                |
| `.html/.htm` | `docling`              | structured documents                |
| unknown   | `auto` (Auto routing)      | no rule; fall through               |

The triage decision is recorded in the `triage_decision`,
`triage_reason`, and `triage_engine` state fields and
visible in the audit log. The recommendation is only
applied when `ocr_provider_id == "auto"`; explicit caller
selections are never overridden.
