# Paperplane: Capabilities, Pipeline, and Technical Guide

Paperplane converts PDFs and document images into grounded Markdown and JSON using Luna
drafting, bounded Terra verification, deterministic PyMuPDF geometry, and auditable evidence.

> It is independently inspired by visual ADE and structured parsing concepts. It does not
> call LandingAI or LlamaParse. OpenAI is the only model provider in the active V2 runtime.

## What the application can do

- Accept native and scanned PDFs and enforce configurable upload limits.
- Render every page as a high-resolution image.
- Recover native words and coordinates when a usable PDF text layer exists.
- Detect headings, columns, text, lists, tables, figures, charts, headers, and footers as bounded regions.
- Process regions independently so complex layouts are not flattened into one OCR stream.
- Snap native PDF text exactly and use OpenAI vision for scanned or ambiguous content.
- Reconstruct headings, paragraphs, lists, tables, figures, and multi-column reading order as Markdown.
- Produce clean Markdown, grounded Markdown, RAG context chunks, an annotated bounding-box PDF, figure crops, layout data, and quality diagnostics.
- Review alignment and retry failed regions through a bounded LangGraph correction loop.
- Persist jobs, page checkpoints, artifacts, retries, cancellation, and safe partial progress.
- Export tamper-evident audit manifests and private evidence/replay bundles.
- Execute generic inline JSON Schema extraction and expose an invoice-v1 preset.
- Expose the workflow through FastAPI, server-sent events, and a Next.js interface.

## End-to-end pipeline

```text
PDF upload
  -> create durable parse job
  -> ingest_and_render
  -> visual_segmentation
  -> zone_processing
  -> layout_stitching
  -> self_reflection
       |-- repair required and attempts remain -> zone_processing
       `-- accepted or repair limit reached ----> finalize
  -> persist Markdown, context, figures, diagnostics, and status
```

### 1. Upload and job creation

`POST /api/parse-jobs` validates the file, creates a database job, saves the source, and returns `202 Accepted` with a job ID. Parsing runs asynchronously. Clients can poll the job or consume its SSE stream. Default limits are 200 MB and 500 pages; oversized PDF canvases and image frame sets above the decoded-pixel budget are rejected before rendering.

Reusable extraction schemas support bounded structural and scalar constraints but reject regular-expression `pattern` rules. Browser previews load text and JSON artifacts only up to 2 MB; larger artifacts remain available as downloads.

### 2. `ingest_and_render`

The parser opens the PDF with PyMuPDF, checks its page count, renders pages to PNG, and extracts native word coordinates when possible. Page images and native words remain connected to their source coordinates for later grounding.

### 3. `visual_segmentation`

Each page is treated as a visual canvas. Segmentation assigns each region a type, confidence, page number, bounding box, and preliminary reading order. Native coordinates are reused when reliable; visual analysis supplies structure for scans and complex pages.

### 4. `zone_processing`

Regions are processed independently under a configurable concurrency limit:

- text regions can use native extraction or OCR;
- tables can use structured parsing instead of flat OCR;
- figures and charts can be cropped and optionally described;
- repair passes target only the regions named by diagnostics.

This crop-and-reason approach prevents a table, sidebar, or second column from contaminating nearby text.

### 5. `layout_stitching`

The stitcher calculates reading order, applies the marginalia policy, reconstructs Markdown hierarchy, and creates:

- clean Markdown for people and LLM input;
- grounded Markdown linked to source regions;
- structured context chunks for RAG and indexing;
- layout JSON for inspection;
- figure and chart crops.

This stage is LlamaParse-inspired: its objective is semantic document structure, not a raw OCR token stream.

### 6. `self_reflection`

A deterministic checker looks for layout problems such as invalid regions, overlaps, missing content, broken ordering, or malformed tables. When the Ollama reviewer is available, it compares the rendered page with its reconstructed Markdown and returns page and region verdicts.

Failed regions become targeted repair instructions such as `p3:table-2:vlm_alignment`. LangGraph routes state back to `zone_processing` while the repair budget remains. The default maximum is two repair passes.

### 7. `finalize`

Finalization records unresolved warnings and sets the terminal state to `completed` or `completed_with_warnings`. Artifacts and diagnostics remain available when a page needs human review.

## How LangGraph is used

Yes, Paperplane uses LangGraph. The workflow is a `StateGraph(ParserState)` in `backend/app/services/extraction/graph.py`.

LangGraph provides explicit nodes and edges, typed shared state, conditional repair routing, bounded recursion, optional durable checkpoints, and a clean boundary between orchestration and parsing engines.

| State property | Purpose |
|---|---|
| `source_path`, `work_dir` | Source PDF and isolated artifact directory |
| `page_images` | Rendered page PNGs |
| `native_words` | Coordinate-aware native PDF words |
| `zones` | Detected and processed page regions |
| `layout` | Document-wide structural representation |
| `markdown` | Clean final Markdown |
| `grounded_markdown` | Markdown connected to source regions |
| `context` | LLM/RAG-ready chunks and schema version |
| `reviews` | Page and region quality verdicts |
| `repair_issues`, `repair_count` | Targeted correction state |
| `warnings`, `status` | Operational and terminal outcome |

## Hybrid visual and structural design

### LandingAI ADE-inspired behavior

Paperplane adopts the vision-first idea that a page should be understood spatially before it is linearized. Bounding boxes, page images, crops, region-specific processing, and visual review are central to the design.

### LlamaParse-inspired behavior

Paperplane aims to produce clean, hierarchical, embedding-friendly Markdown: headings remain headings, tables remain tables, figures retain references, and regions follow reading order rather than raw OCR order.

### Local implementation

The application does not require OpenAI, Anthropic, Gemini, LandingAI, or LlamaParse credentials. Visual inference runs through local Ollama models. This improves privacy and cost control; the trade-off is that throughput and quality depend on local hardware and model availability.

## Models and parsing engines

| Component | Default or role |
|---|---|
| PyMuPDF | Primary rendering and native coordinate extraction |
| pdf2image | Alternative PDF-to-image capability |
| PaddleOCR | Local OCR capability |
| Docling | Structured document and table-processing capability |
| Ollama GLM-OCR | Visual OCR for difficult crops; default `glm-ocr:latest` |
| Ollama reviewer | Page/Markdown alignment review; default `qwen3.5:9b` |

The reviewer is not the primary OCR engine. Its role is to judge reconstruction quality and identify regions that need another pass. A vision-capable model is recommended whenever page images are part of the review.

## Technology stack

| Layer | Technology | Responsibility |
|---|---|---|
| API | FastAPI | Uploads, job control, diagnostics, and artifacts |
| Orchestration | LangGraph | State, nodes, checkpoints, and repair routing |
| PDF | PyMuPDF, pdf2image | Rendering and coordinates |
| OCR/layout | PaddleOCR, Docling | OCR and structured region processing |
| Local inference | Ollama, GLM-OCR, Qwen | Visual extraction and review |
| Contracts | Pydantic | Validated API and internal models |
| Persistence | SQLite, async SQLAlchemy | Jobs, pages, reviews, and artifact metadata |
| Migrations | Alembic | Database schema evolution |
| HTTP | HTTPX | Async Ollama communication |
| Operations | structlog | Structured logs |
| Frontend | Next.js, React, TypeScript, Tailwind CSS | Upload, progress, diagnostics, downloads |
| Packaging | uv, Hatchling | Locked dependencies and Python builds |
| Runtime | Docker Compose | Backend and Ollama services |

## Job lifecycle and durability

```text
queued -> processing -> reflecting -> completed
                         |            completed_with_warnings
                         |            failed
                         `----------> cancelled
```

SQLite stores job and page state. LangGraph checkpoint data supports durable progress. Users can cancel active work, resume eligible jobs, or retry only failed pages. Heavy runtime objects are application-scoped rather than recreated per request.

## API surface

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/parse-jobs` | Upload and enqueue a PDF |
| `GET` | `/api/parse-jobs` | List recent jobs |
| `GET` | `/api/parse-jobs/{id}` | Retrieve job, page, and artifact state |
| `GET` | `/api/parse-jobs/{id}/events` | Receive SSE job snapshots |
| `GET` | `/api/parse-jobs/{id}/pages/{page}/diagnostics` | Read page diagnostics |
| `GET` | `/api/parse-jobs/{id}/artifacts/{type}` | Download an artifact |
| `GET` | `/api/parse-jobs/{id}/figures/{region_id}` | Download a figure crop |
| `POST` | `/api/parse-jobs/{id}/cancel` | Cancel queued or active work |
| `POST` | `/api/parse-jobs/{id}/resume` | Resume an eligible job |
| `POST` | `/api/parse-jobs/{id}/retry-failed` | Retry failed pages |
| `DELETE` | `/api/parse-jobs/{id}` | Delete an inactive job and its files |

FastAPI exposes interactive OpenAPI documentation at `/docs`.

Artifact responses include stable filenames, checksums, download URLs, and inline preview URLs where the MIME type is browser-readable. The UI presents every public artifact in an output gallery. PDFs, images, Markdown, text, and JSON are previewable; ZIP bundles are download-only.

## Output files in the UI

The responsive **Output files** gallery lists every public artifact with its filename, purpose, size, preview action, and individual download. It selects the Annotated PDF first when available, retains the existing quick Markdown preview, resets safely when users switch jobs, and collapses to a single-column viewer on smaller screens.

## Output artifacts

| Artifact | Intended use |
|---|---|
| Annotated PDF (`grounding_pdf`) | Required source-page overlay with type-colored boxes, region IDs, and types |
| Clean Markdown | Reading, LLM context, and general ingestion |
| Grounded Markdown | Traceable content linked to source regions |
| Context JSON | Structured chunks for RAG and vector indexing |
| Layout JSON | Debugging and downstream spatial processing |
| Diagnostics JSON | Quality status, warnings, scores, and repair evidence |
| Figure crops | Charts, diagrams, images, and multimodal retrieval |
| Page images | Visual audit and reviewer input |

## Good use cases

- RAG and knowledge-base ingestion;
- research papers and technical manuals;
- scanned books and archived documents;
- financial or operational reports;
- policies, contracts, and table-heavy PDFs;
- multi-column documents;
- local or privacy-sensitive document processing.

## Important boundaries

Paperplane supports optional schema-first field extraction in addition to faithful document reconstruction. Saved restricted Draft 2020-12 schemas can contain nested objects, arrays, and table arrays. Results preserve page, region, bounding-box, and table-cell citations; large tables are also exported as grounded JSONL. Incomplete or invalid instances remain auditable partial outputs and complete the parse with warnings.

Quality depends on scan resolution, rotation, language support, local GPU capacity, model quality, and table complexity. A `completed_with_warnings` result means output was produced but one or more diagnostics should be reviewed.

The default SQLite deployment is intended for local and single-worker operation. `job_max_concurrent` is limited to one; distributed workers would require a different coordination and persistence design.

## Continue reading

- [Project README](../README.md) - installation and quick start
- [Architecture](ARCHITECTURE.md) - implementation structure
- [Quality](QUALITY.md) - diagnostics and quality behavior
- [Limitations](LIMITATIONS.md) - known constraints
- [Runbook](RUNBOOK.md) - operational procedures
- [How Paperplane works](how-it-works.md) - end-to-end processing journey
- [Zero to Mastery](ZERO_TO_MASTERY.md) - guided codebase tutorial and exercises
- [Run Paperplane](RUN_APP.md) - command-only PowerShell and Bash reference
