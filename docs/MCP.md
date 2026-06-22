# MCP Server Guide (v0.6.0)

This document explains how to run and use the Agentic Document Extraction
MCP server end to end.

The MCP server exposes four tools from the v0.5.0 extraction stack:

- `extract_document`
- `verify_extraction`
- `resolve_entities`
- `eval_golden_set`

It runs over stdio and can be used by MCP clients such as Claude Desktop,
Cursor, Cline, and Continue.

---

## 1) Prerequisites

- Python `3.12.x`
- `uv`
- Project checked out locally
- Optional: `OLLAMA_BASE_URL` + a local Ollama model for live extraction

---

## 2) Install

From the repository root:

```bash
uv venv --python 3.12.10 .venv
source .venv/bin/activate
uv pip install -e ".[mcp]"
```

Optional extras:

```bash
# image OCR providers
uv pip install -e ".[paddleocr]"

# local ollama integrations
uv pip install -e ".[ollama]"
```

---

## 3) Run MCP server

Use any one of these:

```bash
# justfile recipe
just mcp

# module entry
PYTHONPATH=. .venv/bin/python -m app.mcp_server

# installed script entrypoint
ade-mcp
```

The server blocks on stdio until your MCP client connects.

---

## 4) MCP client configuration

## Claude Desktop (example)

Add to your MCP config JSON:

```json
{
  "mcpServers": {
    "agentic-document-extraction": {
      "command": "/ABSOLUTE/PATH/Agentic-Document-Extraction/.venv/bin/python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/ABSOLUTE/PATH/Agentic-Document-Extraction",
      "env": {
        "PYTHONPATH": "."
      }
    }
  }
}
```

## Cursor / Cline / Continue

Use equivalent command + args:

- command: `/ABSOLUTE/PATH/.../.venv/bin/python`
- args: `-m app.mcp_server`
- cwd: repo root
- env: `PYTHONPATH=.`

If your client supports command string only, use:

```bash
bash -lc 'cd /ABSOLUTE/PATH/Agentic-Document-Extraction && PYTHONPATH=. .venv/bin/python -m app.mcp_server'
```

---

## 5) Tool reference

## `extract_document`

Runs parse -> extract -> evidence grounding -> verifier -> confidence merge.

Required input:

- `path`: local file path
- `schema_fields`: array of field definitions (`name` required)

Common optional input:

- `ocr_provider`: `auto | pymupdf | paddleocr | glmocr | docling`
- `llm_provider`: `auto | openai | gemini | anthropic | ollama`
- `enable_verifier`: boolean
- `enable_layout_parsing`: boolean
- `min_evidence_score`: `0.0..1.0`
- `use_llm_verifier`: boolean

Example:

```json
{
  "path": "./samples/invoice.txt",
  "schema_fields": [
    {"name": "vendor_name", "kind": "string"},
    {"name": "invoice_number", "kind": "id"},
    {"name": "total", "kind": "currency"}
  ],
  "llm_provider": "ollama",
  "ocr_provider": "auto"
}
```

Output includes:

- `fields`
- `evidence` (page/bbox/text_span/evidence_score)
- `not_found`
- `verifier`
- `_meta.composite_confidence`

## `verify_extraction`

Re-runs verifier over an evidence map.

Required input:

- `evidence`: `{field: {value, page, bbox, text_span, evidence_score}}`
- `document_text`: full source text

Optional:

- `use_llm`: boolean

Output includes `field_verdicts`, `disputed_fields`, `needs_human_review`.

## `resolve_entities`

Clusters mentions across pages and returns canonical forms.

Required input:

- `mentions`: list of `{text, page?, bbox?, region_id?, field?}`

Optional:

- `entity_type`
- `jaccard_threshold`

Output includes `entities[]` with canonical form + clustered mentions.

## `eval_golden_set`

Scores predictions against a manifest-backed golden set.

Required input:

- `manifest_path`

Optional:

- `predictions`: `{sample_id: prediction}`

If `predictions` omitted, tool reads `prediction.jsonl` next to manifest.

Output includes:

- counts (`n_samples`, `n_with_predictions`)
- `end_to_end_task_success_rate`
- score metrics when available (`token_f1`, `teds`, `cell_f1`, `mean_bbox_iou`, ...)

---

## 6) End-to-end smoke workflow

1. Start server with `just mcp`.
2. Connect MCP client and call `extract_document` on a local `.txt` or `.pdf`.
3. Feed returned `evidence` + text into `verify_extraction`.
4. Call `resolve_entities` on repeated names from multi-page docs.
5. Run `eval_golden_set` on `eval/golden_set/v2/manifest.json` with your predictions.

Quick local test command:

```bash
PYTHONPATH=. .venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
```

---

## 7) Troubleshooting

## `ImportError: The MCP extra is not installed`

Install the extra:

```bash
uv pip install -e ".[mcp]"
```

## `ModuleNotFoundError: app`

Start from repo root and set `PYTHONPATH=.`.

## `file not found` in `extract_document`

The path is resolved on MCP server host filesystem. Pass absolute path or correct
client working directory.

## Image OCR error in `extract_document`

Base install supports text-ish files + PDFs. For image OCR, install OCR extras and
configure providers.

## `no predictions provided and prediction.jsonl not found`

Pass `predictions` argument explicitly or create `prediction.jsonl` next to the
manifest.

## `extractor failed` with provider selection

Use `llm_provider="ollama"` for live local model path, or `auto` for deterministic
fallback behavior when no live provider is configured.

---

## 8) Operational notes

- MCP server is local-process stdio service. It inherits your shell environment.
- Do not expose API keys in MCP client config files committed to git.
- For production automation, pin project commit/tag and lock dependency install.

---

## 9) Validation checklist

Before shipping:

```bash
PYTHONPATH=. .venv/bin/python -m pytest backend/tests/test_mcp_server.py -q
.venv/bin/ruff check backend/app backend/tests scripts
.venv/bin/ruff format --check backend/app backend/tests scripts
```
