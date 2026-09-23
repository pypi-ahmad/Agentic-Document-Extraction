---
type: Integration
title: Processing engines, providers, and cost
description: How Paperplane selects a processing engine and model, composes local and cloud adapters, reads credentials, and estimates current-session cost.
tags: [engines, providers, cost]
verified:
  - by: openwiki/0.5.2
    at: 2026-09-23T15:07:44.901Z
sources:
  - id: openwiki-source-189d62570c2f36624ef6e5e5
    resource: repo://app_pages/cost.py
  - id: openwiki-source-622d077668845732e7510c74
    resource: repo://paperplane/ade_contracts.py
  - id: openwiki-source-f49282088ebd2631c00aa01b
    resource: repo://paperplane/model_catalog.py
  - id: openwiki-source-0be235675c6163e76238f15b
    resource: repo://paperplane/ollama_document.py
  - id: openwiki-source-c454053fe0ca1fd8d297ff5a
    resource: repo://paperplane/parser.py
  - id: openwiki-source-e145d6f0c3ed02aaf6b310dd
    resource: repo://paperplane/pipeline.py
  - id: openwiki-source-541a9e49a6db4313a22a5ad3
    resource: repo://paperplane/runtime.py
  - id: openwiki-source-964922c41d4be25ac5f159ec
    resource: repo://streamlit_app.py
  - id: openwiki-source-bf4290575943b5a279a1aa5d
    resource: repo://tests/test_model_migration.py
generated: { by: "codex", at: "2026-09-23T15:07:44.901Z" }
---

# Processing engines, providers, and cost

## Engine selection

The Parse page offers four mutually exclusive engines: Docling, PDF Inspector, Cloud AI, and Ollama. Cloud enhancement can be added after Docling, PDF Inspector, or Ollama; it is not a second option alongside Cloud AI. The UI maps these choices to processing strategies such as `docling_ai`, `pdf_inspector_ai`, and `ollama_ai`.

`EngineOptions` enforces the same one-engine rule in the contract layer. PDF Inspector strategies accept PDF files only. Cloud enhancement is opt-in. If Docling or PDF Inspector raises an input error during an `_ai` strategy, the parser records a warning and sends the selected pages through AI processing. After successful local parsing, it selects pages for refinement based on parser confidence and page content.

## Adapter composition and data paths

`runtime.parse_document` resolves the selected cloud model through `model_catalog.py`, then maps its provider to an adapter. Cloud adapters cover OpenAI, xAI, Google, Anthropic, and Agnes. A cloud parse sends rendered images for selected pages to the chosen provider adapter. Docling and PDF Inspector perform their parsing locally. Ollama sends image content to `OLLAMA_BASE_URL`, which defaults to loopback; if configured to a remote server, the request goes there. The UI checks model capabilities and disables parsing when a model does not report vision support.

For `ollama_ai`, the runtime chains local Ollama processing with the selected cloud adapter. For Docling and PDF Inspector enhancement, the parser retains successful local pages and sends only pages chosen for refinement. Review [Parse workflow and grounded assembly](../workflows/parse-document.md) for page-selection and refinement rules.

## Catalog and credentials

`paperplane/model_catalog.py` is the code source for supported cloud model IDs, labels, provider names, credential environment-variable names, documentation links, and configured token rates. The Parse page reads the selected model's credential from its configured environment variable or Streamlit secrets. Google also has a legacy `GEMINI_API_KEY` fallback. This page does not reproduce secret values or pricing tables; consult the [model guide](../../docs/MODELS.md) for the current catalog presentation.

## Usage and cost estimates

Adapters return provider-reported token usage. The Parse page records usage by job in Streamlit session state, and the Cost page aggregates it by model for that browser session. It displays input, cached-input, cache-write, and output tokens.

`estimate_model_cost` applies the rates stored in the model catalog. It separates cached and cache-write input when the model defines those rates, clamps negative token counts to zero, and returns a configured estimate. The display is an estimate based on the catalog, not a provider invoice.

## Related pages

- [Grounding, contracts, and exports](../concepts/contracts-and-exports.md)
- [Parse workflow and grounded assembly](../workflows/parse-document.md)
- [Setup and model storage](../operations/setup-and-model-store.md)
