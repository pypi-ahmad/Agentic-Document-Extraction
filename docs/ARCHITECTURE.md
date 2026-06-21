# Architecture

> A reference for engineers reading or extending the codebase.

This document is a zero-to-hero walkthrough: it explains **what** the
project is, **why** it is built the way it is, **how** the code
implements it, and **where** the real outputs prove it works.

---

## 1. Definition

**Agentic Document Extraction** is a local-first service that turns
unstructured documents (PDF, PNG, JPEG, TIFF) into structured JSON
that conforms to a user-defined schema. It is *agentic* in the sense
that the work is broken into a state machine of cooperating steps,
each of which can fail, retry, or hand off to a human — rather than
being a single opaque model call.

The user-facing workflow is:

1. Upload a document.
2. Pick or define a schema (set of named fields with types).
3. Run extraction; the system parses the file, calls an LLM,
   validates the output, and assigns a confidence score to every
   field.
4. Review low-confidence fields inline; approve, correct, or reject.

The whole thing runs against a local SQLite file. No cloud, no
account, no telemetry.

---

## 2. Why this shape

### 2.1 The pipeline is the product

Most "extract structured data from a PDF" tools are a single prompt
to a single model. That breaks down the moment:

- the file is multi-page and the LLM has a context-window cap;
- the layout changes (different vendors, different templates);
- you need an audit trail (which step failed, how long it took, did
  the LLM actually see the text?);
- you want to swap a model without rewriting your app.

So the work is partitioned into four explicit nodes — `parse`,
`extract`, `validate`, `finalize` — coordinated by a LangGraph
`StateGraph`. Each node returns a typed dict; the graph carries
state between them; the runtime persists a per-node row in
`extraction_steps` so the UI can show live progress and a
post-mortem timeline.

### 2.2 Confidence is a first-class output

Every LLM extraction is asked to return, alongside the structured
data, a `_confidence` map: field name → 0.0–1.0 score. The
`validate` node uses that map plus a configurable threshold
(`CONFIDENCE_THRESHOLD`, default 0.6) to decide whether the
extraction auto-completes or is routed to `needs_review`.

This means the LLM is not the source of truth for "is this
extraction good enough?" — it is one signal among several. The
final say belongs to the reviewer.

### 2.3 Pluggable engines beat monolithic models

Three LLM providers (OpenAI, Gemini, Claude) and three OCR engines
(PyMuPDF, PaddleOCR, GLM-OCR) ship in the box. They all conform to
small abstract bases, so adding a fourth is local:

- `app/services/llm/base.py::BaseLLMProvider` — 1 abstract method
  for extraction, 1 for dynamic model listing.
- `app/services/ocr/base.py::BaseOCRProvider` — 1 abstract method
  for `extract_text`. The rest are derived from class attributes
  (`provider_id`, `display_name`, `supported_file_types`,
  `feature_flag_name`).

The registry (`app/services/llm/registry.py`,
`app/services/ocr/registry.py`) is the single point of contact for
the rest of the code. It handles:

- feature flags (`ENABLE_PADDLEOCR`, `ENABLE_GLM_OCR`)
- dependency presence (`paddleocr` installed or not, `ollama`
  reachable or not)
- file-type compatibility (PyMuPDF refuses to OCR an image; the
  Auto router refuses to fall back from image OCR to PyMuPDF)
- deterministic `auto` resolution

### 2.4 Local-first by design

Everything you upload, every schema you create, every extraction and
review you run lives in one SQLite file. That makes it trivial to
back up, fork, throw away, or hand to a colleague. It also makes the
state machine honest: there is no in-memory "current job" that
disappears when the process restarts.

---

## 3. How the code implements it

### 3.1 Process topology

```
backend/app/
├── main.py                 # FastAPI app, lifespan, startup recovery
├── config.py               # Pydantic Settings (env + .env)
├── database.py             # Async SQLAlchemy engine + session
├── models/                 # ORM + Pydantic schemas + enums
│   ├── db_models.py        # Document, Extraction, ExtractionStep, …
│   ├── enums.py            # StrEnum: ParserEngine, LLMProviderID, …
│   ├── schemas.py          # Request/response Pydantic v2 models
│   └── extraction/_base.py  # ValidationResult
├── routers/                # FastAPI routers (one per resource)
│   ├── documents.py
│   ├── schemas.py
│   ├── extractions.py      # includes SSE streaming + review
│   └── providers.py
├── services/
│   ├── extraction/
│   │   ├── graph.py        # The LangGraph state machine
│   │   ├── validation.py   # Field-level validators + business rules
│   │   ├── business_rules.py
│   │   ├── error_classify.py
│   │   └── presets.py      # Built-in schemas
│   ├── llm/
│   │   ├── base.py         # BaseLLMProvider + LLMProviderError
│   │   ├── openai_provider.py
│   │   ├── gemini_provider.py
│   │   ├── claude_provider.py
│   │   ├── output_parser.py
│   │   ├── prompts.py
│   │   └── registry.py
│   └── ocr/
│       ├── base.py         # BaseOCRProvider + OCRResult
│       ├── pymupdf_provider.py
│       ├── paddleocr_provider.py
│       ├── glm_ocr_provider.py
│       └── registry.py
└── utils/file_handler.py

frontend/src/
├── app/                    # Next.js app router pages
├── components/             # React components
└── lib/api.ts              # Typed API client + enums
```

### 3.2 The extraction state machine

```python
# backend/app/services/extraction/graph.py

class PipelineState(TypedDict, total=False):
    # inputs
    file_path: str
    schema_fields: list[dict]
    ocr_provider_id: str
    llm_provider_id: str
    llm_model_id: str
    # outputs from each node
    ocr_text: str
    ocr_provider_used: str
    extracted_data: dict[str, Any]
    llm_provider_used: str
    llm_model_used: str
    confidence: dict[str, float]
    extract_attempts: int
    validation_errors: list[str]
    validation_results: list[dict]
    review_verdict: str            # "valid" | "needs_review"
    status: str                    # "queued" | "processing" | "ocr_complete" | …
    error: str
    completed_at: str
```

The four nodes:

| Node        | Reads                                  | Writes                                                                                  | Failure mode                                    |
| ----------- | -------------------------------------- | --------------------------------------------------------------------------------------- | ----------------------------------------------- |
| `parse`     | `file_path`                            | `ocr_text`, `ocr_provider_used`, `status="ocr_complete"`                                | returns `{"status": "failed", "error": ...}`    |
| `extract`   | `ocr_text`, `schema_fields`            | `extracted_data`, `confidence`, `llm_provider_used`, `llm_model_used`, `extract_attempts` | retries on retryable errors, then fails         |
| `validate`  | `extracted_data`, `schema_fields`, `confidence` | `validation_results`, `validation_errors`, `review_verdict`                  | never fails the pipeline; flags fields          |
| `finalize`  | `review_verdict`                       | `status` (`completed` or `needs_review`), `completed_at`                                | raises if `review_verdict` is missing/wrong    |

The graph itself:

```python
graph = StateGraph(PipelineState)
graph.add_node("parse", parse_node)
graph.add_node("extract", extract_node)
graph.add_node("validate", validate_node)
graph.add_node("finalize", finalize_node)
graph.add_edge(START, "parse")
graph.add_conditional_edges("parse",    _after_parse,    {"extract": "extract", "end": END})
graph.add_conditional_edges("extract",  _after_extract,  {"validate": "validate", "end": END})
graph.add_edge("validate", "finalize")
graph.add_edge("finalize", END)
extraction_graph = graph.compile()
```

The `parse` and `extract` nodes short-circuit straight to `END` on
failure so the terminal status is whatever they wrote.

### 3.3 Pipeline driver

`backend/app/routers/extractions.py::_run_extraction_pipeline` is the
outer driver. It opens its own DB session (not the request session,
because the job runs after the HTTP response), sets the row to
`processing`, and consumes `extraction_graph.astream(stream_mode="updates")`.
For every node it receives, it:

1. Marks the *previous* step row `completed` (or `failed` if the
   node set `status="failed"`), records `duration_ms`.
2. Inserts the *next* step row as `running` with the current UTC
   timestamp.
3. Persists the cumulative state on the `extraction` row so the SSE
   stream and the history page see intermediate progress.

The whole thing is wrapped in `asyncio.wait_for(timeout=_JOB_TIMEOUT)`
(default 300 s). A timeout or unexpected exception marks the
extraction `failed` and finalizes any `running` steps.

### 3.4 SSE streaming

`/api/extractions/{id}/stream` polls the DB every 1 s, emits a
`data:` frame only when the `status` or the set of `(name, status,
error, duration_ms, completed_at)` tuples actually changes, and
closes the stream when the status is terminal. The frontend's
detail view uses this; the history list uses plain polling.

### 3.5 LLM provider contract

```python
# backend/app/services/llm/base.py
class BaseLLMProvider(ABC):
    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @abstractmethod
    def get_api_key(self) -> str: ...

    @abstractmethod
    def is_extraction_client_available(self) -> bool: ...

    @abstractmethod
    async def _list_models_dynamic(self) -> list[LLMModel]: ...

    @abstractmethod
    async def extract(
        self, text: str, schema_fields: list[dict], model_id: str = "auto",
    ) -> ExtractionResult: ...
```

`ExtractionResult` carries `data` (the parsed dict), `raw_response`
(unparsed LLM text — useful for debugging), `model_used`,
`provider`, `usage` (token counts if available), and `confidence`
(the `_confidence` map stripped out of `data`).

The base class implements `list_models()` and `get_status()` so
concrete providers only need to implement extraction, the dynamic
listing, and a few identity properties.

Auto resolution prefers the configured `DEFAULT_LLM_PROVIDER` when
ready, otherwise walks `AUTO_PRIORITY = (openai, gemini, anthropic)`
and returns the first ready provider. If nothing is ready, the
extraction fails fast with a clear "no provider ready" error.

### 3.6 OCR provider contract

```python
# backend/app/services/ocr/base.py
class BaseOCRProvider(ABC):
    feature_flag_name: str | None = None    # attribute, not @property
    is_user_selectable: bool = True
    supported_file_types: frozenset[str] | None = None

    @property
    @abstractmethod
    def provider_id(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @abstractmethod
    async def extract_text(self, file_path: Path) -> OCRResult: ...

    def is_available(self) -> bool: ...        # default True
    def supports_file_type(self, file_type: str | None) -> bool: ...
```

`OCRResult` is normalised in `__post_init__`: if you only set `text`
or only set `page_results`, the other is filled in automatically;
`raw` and `metadata` are kept in sync; the per-page `blocks`/`tables`
flatten into the top-level `blocks`/`tables` for convenience.

Auto resolution in `app/services/ocr/registry.py` walks
`AUTO_PRIORITY = (glmocr, paddleocr, pymupdf)` and for each candidate
checks: (1) the feature flag is on, (2) the runtime is available, (3)
the file type is supported. PDF goes to PyMuPDF (which is
PDF-only); images try GLM-OCR → PaddleOCR. The router **never** falls
back from an image OCR engine to PyMuPDF — that would be unsafe.

### 3.7 Persistence model

```sql
-- Five tables, simple relationships.
documents
  id, filename, original_filename, file_path, file_type,
  file_size, page_count, status, created_at

extraction_schemas
  id, name (UNIQUE), description, fields (JSON), created_at, updated_at

extractions
  id, document_id → documents.id, schema_id → extraction_schemas.id,
  ocr_provider, llm_provider, llm_model, status,
  ocr_text, result (JSON), validation_errors (JSON),
  validation_results (JSON), review_verdict, error,
  ocr_provider_used, llm_provider_used, llm_model_used,
  confidence (JSON), extract_attempts, error_category,
  created_at, started_at, completed_at, reviewed_at

extraction_steps
  id, extraction_id → extractions.id (CASCADE),
  name, status, started_at, completed_at, duration_ms, error

extraction_reviews
  id, extraction_id → extractions.id (CASCADE),
  decision, corrected_fields (JSON), notes, created_at
```

`init_db()` enables WAL mode and runs `PRAGMA optimize` on startup.
WAL is what makes the SSE poller and the background pipeline safe
to read and write the DB concurrently.

### 3.8 Startup recovery

`main.py::_recover_orphaned_jobs` runs once at startup. It looks
for any `extraction` whose status is in
`("queued", "processing", "ocr_complete", "extracted")` and marks
them `failed` with `error="Server restarted while this job was
running. Please retry."`. The same sweep finalises any
`extraction_steps` rows that are still `running`. The user sees
these jobs in the history list and can retry them.

### 3.9 Error classification

`app/services/extraction/error_classify.py` tags errors as one of
`auth | rate_limit | timeout | parse_error | provider_error |
file_error | validation | unknown`. The router stores the tag on
`extractions.error_category` so the UI can group failures and
distinguish "fix the document" from "retry later" cases.

### 3.10 Frontend

The Next.js app is a thin client over the FastAPI API. The
`/api/providers/config` endpoint is the single source of truth for
the parser dropdown, the LLM dropdown, the file types, and the
upload size limit — the UI never hard-codes those. The extraction
detail page subscribes to the SSE stream and falls back to polling
on disconnect; the history page uses polling only.

---

## 4. How the real outputs prove it

End-to-end tests and live provider validations live under
`backend/tests/`. Notable coverage:

| File                                | Asserts                                                                                       |
| ----------------------------------- | --------------------------------------------------------------------------------------------- |
| `test_extraction_graph.py`          | The four nodes produce the expected state transitions; the Auto router works for each provider. |
| `test_ocr_registry.py`              | The registry returns the right engine for each file type and respects every feature flag.      |
| `test_llm_registry.py`              | Auto resolution prefers the configured default, falls back to the priority order, fails fast. |
| `test_durability.py`                | Crashed jobs are recovered on startup; partial step rows are finalised.                       |
| `test_sse_and_cache.py`             | The SSE stream emits one frame per real change; live endpoints set `Cache-Control: no-store`. |
| `test_validation.py`                | Required-field, type, and confidence rules all flag correctly.                                |
| `test_business_rules.py`            | The pluggable rule registry (e.g. financial-totals check) runs.                                |
| `test_output_parser.py`             | Markdown-fenced JSON, trailing commas, and nested objects all parse.                           |
| `test_providers.py`                 | All three LLM providers and their model-listing behaviour match the documented contract.       |
| `test_glm_ocr_provider.py`          | The local GLM-OCR provider cleans layout noise, probes Ollama, and routes correctly.           |

Run them all with:

```bash
source .venv/bin/activate
pytest backend/tests/ -q
```

Expected: **359 passed** at the time of writing.

The `scripts/validate_llm_providers.py` and
`scripts/e2e_validation.py` scripts are the *live* counterparts: they
spin up real provider clients and a running backend, and confirm
that the production flow (upload → schema → extract → review) works
end-to-end against the configured keys.
