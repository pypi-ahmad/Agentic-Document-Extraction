# Architecture

Paperplane 5.3.0 runs as one local Streamlit process with a framework-neutral Python
package. It has no JavaScript frontend or public HTTP API. SQLite stores local job metadata;
private inputs and artifacts live in `%LOCALAPPDATA%\Paperplane` and expire after seven
days.

```mermaid
flowchart LR
  Browser --> Navigation[Streamlit navigation]
  Navigation --> Parse
  Navigation --> Organize
  Navigation --> Jobs
  Navigation --> Cost[session usage and cost]
  Parse --> Runtime[bounded parallel runtime]
  Runtime --> Engines{explicit engine}
  Engines --> Docling
  Engines --> Inspector[PDF Inspector]
  Engines --> Cloud[cloud vision]
  Engines --> Ollama[local Ollama vision]
  Docling --> Assemble
  Inspector --> Assemble
  Cloud --> Assemble
  Ollama --> Layout[PP-DocLayoutV3 regions]
  Layout --> OllamaOCR[Ollama crop recognition]
  OllamaOCR --> Assemble
  Assemble --> Intelligence[cross-page relations]
  Intelligence --> Contracts[ADE v2 + Paperplane v5]
  Contracts --> Outputs[Markdown / HTML / JSON / annotated PDF / batch ZIP]
  Contracts --> Workflows[Classify/Split/Section]
  Contracts --> Store[(SQLite + private artifacts)]
  Contracts --> Cost
```

## Boundaries

- `workspace_app.py` owns navigation; `streamlit_app.py` is the Parse page.
- `runtime.py` composes providers and processes files concurrently; files never share
  context. Optional progress events identify document start, finalized pages, and document
  completion without coupling the runtime to Streamlit.
- `agnes_document.py` sends selected page PNGs inline in Agnes Chat Completions requests;
  it does not publish uploads at separate URLs.
- `ollama_ocr.py` detects PP-DocLayoutV3 regions on CPU, selects family-native OCR prompts,
  crops/rotates regions, and cleans bounded local model output.
- `ollama_document.py` bounds DeepSeek retries, skips isolated exhausted regions with
  warnings, and stops sustained local failures before processing every remaining crop.
- `parser.py` applies page ranges and allows only previous selected pages to inform later
  page processing.
- `contracts.py` is the internal grounded representation; `ade_contracts.py` produces
  strict zero-based ADE v2-style JSON and the namespaced Paperplane export.
- Per-model token usage flows through the grounded contract into a browser-session ledger;
  Cost applies configured rates without retaining document content.
- `ade_workflows.py` implements cited Classify, Split, and Section organization workflows.
- `jobs.py` is a future-HTTP-wrappable service boundary for durable lifecycle, checkpoints,
  retention, and deletion.
- `document_intelligence.py`, `calibration.py`, and `benchmark.py` keep semantic relations,
  confidence, and evaluation explicit and independently testable.
- `outputs.py` converts model-produced Markdown to allowlist-sanitized standalone HTML and
  builds traversal-safe, manifest-versioned batch archives without source uploads.

Block and line grounding is the ADE-compatible interoperability boundary. Observed word
grounding, provenance, confidence status, and cross-page relations are Paperplane
extensions. IDs are stable only within one response.
