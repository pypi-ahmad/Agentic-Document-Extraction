# FAQ

## Is Paperplane Streamlit?

Yes. `workspace_app.py` provides the Parse, Organize, Jobs, and Benchmarks pages.

## Does it use LandingAI ADE?

No. It independently implements an ADE-inspired workflow and versioned v2-style JSON
contracts. It does not call LandingAI or claim accuracy/API drop-in parity.

## Which engine should I choose?

Select one of Docling ADE, PDF Inspector ADE, Cloud AI ADE, or Ollama ADE. All toggles are
off initially and selection is exclusive. PDF Inspector is PDF-only. Cloud enhancement is
optional after a local engine; there is no automatic routing.

## Where are files saved?

The active batch remains in Streamlit session state. Durable job metadata, source files,
result JSON, and annotated PDFs are retained under `%LOCALAPPDATA%\Paperplane` for seven
days. Use Jobs to delete one job or clear all.

## Who is responsible for documents and API keys?

The operator is responsible for every file they choose to process, having permission to
process it, choosing whether selected pages may be sent to a cloud provider, securing their
own API keys, accepting provider terms and charges, validating outputs, and deleting local
artifacts when required. Paperplane is self-hosted; its maintainers do not receive user
documents or credentials through the project.

## Does it have an API or database?

It uses local SQLite for job metadata and filesystem artifacts. There is no HTTP API in
v5; the Python service layer is designed to be wrapped later.

## How does Ollama work?

Paperplane lists all installed models from the local server and enables Parse only when
the selected model advertises vision. Unknown models work but their confidence is raw and
uncalibrated. GLM-OCR, PaddleOCR-VL, and DeepSeek-OCR first receive crops from the local
PP-DocLayoutV3 detector, so their native OCR prompts are not constrained by a whole-page
JSON schema.

DeepSeek retries one empty or transiently failed text crop. A single exhausted crop is
skipped with a visible warning; three consecutive failures stop the page and return a
specific Ollama error instead of the generic unexpected-failure message.

## Which key does Gemini use?

Use `GOOGLE_API_KEY` in the Windows user environment, process environment, ignored `.env`,
or Streamlit secrets. `GEMINI_API_KEY` remains a legacy fallback only when
`GOOGLE_API_KEY` is absent.

Paperplane automatically uses the minimum thinking level supported by the selected Gemini
model (`minimal` for 3.5 Flash-Lite and `low` for 3.7 Flash).

## Can Agnes process private uploads?

Yes. Paperplane sends selected page images inline to Agnes and does not publish them at a
separate public URL.

## Are citations and word boxes guaranteed?

Missing evidence remains missing. Word boxes come only from native PDF text or RapidOCR
word observations that exactly align to Markdown. Organize results retain source ranges or
explicitly report deterministic partials.

## Can files affect one another?

No. Cross-page context is limited to selected pages inside one document. Pages outside the
range and other uploaded files are never used as context.

## Is there a published accuracy score?

Not yet. The checked-in initial benchmark corpus is intentionally too small. Paperplane
publishes no score without raw results and full provenance.
