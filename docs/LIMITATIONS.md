# Limitations

- Local, single-user Streamlit deployment; no authentication, hosted profile, REST API, or
  client drop-in compatibility with LandingAI ADE.
- Job execution still runs inside the Streamlit process. SQLite/checkpoints retain lifecycle
  state, but a stopped process cannot continue computing until the app is running again.
- Retention is seven days under `%LOCALAPPDATA%\Paperplane`; this is not a multi-user
  database or remote object store.
- PDF Inspector accepts PDF only. Legacy DOC/PPT/XLS and encrypted PDFs are unsupported.
- Cloud engines, including Agnes, send selected page images to their provider.
- Files are context-isolated. Only selected pages inside one file share ordered context.
- Word boxes are emitted only from native PDF text or RapidOCR word observations that align
  exactly to Markdown. Missing alignment remains missing.
- Arbitrary Ollama models have raw, explicitly uncalibrated confidence until a matching
  checked-in profile exists.
- Classify/Split/Section deterministic local results may be partial and carry warnings.
- The initial locked benchmark corpus is too small for a comparative accuracy claim. No
  LandingAI parity or production-accuracy claim is made.
- Provider/model IDs and prices may change. UI cost is an estimate, not an invoice.
- Batch ZIPs exclude original uploads. If annotated-PDF generation fails for an otherwise
  successful parse, the other four outputs remain downloadable and the manifest records the
  artifact warning.

Limits: 20 files, 1 GiB combined, six concurrent files, 200 MiB and 500 pages per file,
4,000,000 PDF canvas units per page, and 40,000,000 decoded image pixels.
