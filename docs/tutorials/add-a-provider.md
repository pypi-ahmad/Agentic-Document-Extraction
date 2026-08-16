# Tutorial: add a new cloud AI provider

This tutorial adds a minimal new provider to Paperplane's Cloud AI ADE engine, end to end:
a catalog entry, a provider module implementing the required contract, an environment
variable, and one real parse through the Streamlit UI. By the end you will have a working
(if trivial) fifth provider alongside xAI, OpenAI, Google, Anthropic, and Agnes.

The full field-by-field contract this tutorial builds toward is documented in
[`docs/reference/provider-contract.md`](../reference/provider-contract.md); this page
focuses on getting one example working.

We'll build a stub provider called **Echo**, backed by a fake endpoint you control, so you
can see the wiring without needing a real third-party API key.

## 1. Add the catalog entry

Open [`paperplane/model_catalog.py`](../../paperplane/model_catalog.py). Add `"echo"` to the
`Provider` literal at the top:

```python
Provider = Literal["xai", "openai", "google", "anthropic", "agnes", "echo"]
```

Then append a new `DocumentModel` to the `DOCUMENT_MODELS` tuple
(`paperplane/model_catalog.py:33-101`):

```python
DocumentModel(
    label="Echo (tutorial)",
    model_id="echo-1",
    provider="echo",
    api_key_env="ECHO_API_KEY",
    help_text="Tutorial stub provider — echoes a fixed structured response.",
    docs_url="https://example.invalid/echo-docs",
    input_price_per_million=Decimal("0"),
    output_price_per_million=Decimal("0"),
    pricing_note="Tutorial provider; not billed.",
),
```

Nothing else in `model_catalog.py` needs to change — `DOCUMENT_MODEL_BY_ID` and
`DOCUMENT_MODEL_BY_LABEL` are built automatically from the tuple.

## 2. Write the provider module

Create `paperplane/echo_document.py`. The smallest real provider module in the codebase is
[`paperplane/gemini_document.py`](../../paperplane/gemini_document.py) (166 lines) — use it
as your shape reference. A minimal stub:

```python
"""Tutorial stub provider boundary for grounded document extraction."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

import httpx

from paperplane.openai_document import (
    OpenAIRequestError,
    OpenAIUsage,
    StructuredGeneration,
    _emit_audit,
)

ECHO_MODELS = {"echo-1"}


class EchoRequestError(OpenAIRequestError):
    """Raised when the Echo stub cannot return a structured document result."""


class EchoDocumentAdapter:
    def __init__(self, http: httpx.AsyncClient, *, api_key: str) -> None:
        self.http = http
        self.api_key = api_key

    async def generate_structured(
        self,
        *,
        model: str,
        image: bytes | None,
        instructions: str,
        context: str | None = None,
        schema_name: str,
        schema: dict[str, Any],
        reasoning_effort: Literal["none", "low", "medium", "high"],
        detail: Literal["low", "high", "original"],
        prompt_cache_key: str,
    ) -> StructuredGeneration:
        del context, reasoning_effort, detail, prompt_cache_key
        if model not in ECHO_MODELS:
            raise EchoRequestError(f"Unsupported Echo model: {model}")
        if not self.api_key:
            _emit_audit({"model": model, "status": "error", "error_type": "missing_api_key"})
            raise EchoRequestError("Echo API key is not configured")

        audit_record = {
            "model": model,
            "schema_name": schema_name,
            "schema_sha256": hashlib.sha256(
                json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "instructions": instructions,
            "image_sha256": hashlib.sha256(image).hexdigest() if image is not None else None,
        }
        value = {"markdown": "Echo stub output", "blocks": []}
        _emit_audit({**audit_record, "status": "completed", "value": value})
        return StructuredGeneration(
            value=value,
            usage=OpenAIUsage(),
            latency_ms=0.0,
        )


__all__ = ["ECHO_MODELS", "EchoDocumentAdapter", "EchoRequestError"]
```

This returns a fixed response instead of calling a real endpoint — enough to prove the
wiring end to end. Real providers call an HTTP endpoint through `self.http`; see
`GeminiDocumentAdapter.generate_structured`
([`paperplane/gemini_document.py:43-158`](../../paperplane/gemini_document.py)) for a
complete example that does.

## 3. Wire the adapter into `runtime.py`

Open [`paperplane/runtime.py`](../../paperplane/runtime.py). Import your adapter near the
other provider imports (around line 14-18):

```python
from paperplane.echo_document import EchoDocumentAdapter
```

Add a branch to `cloud_adapter()` (`paperplane/runtime.py:108-125`):

```python
def cloud_adapter(client: httpx.AsyncClient, provider: str) -> StructuredAdapter:
    if provider == "echo":
        return EchoDocumentAdapter(client, api_key=api_key)
    if provider == "agnes":
        return AgnesDocumentAdapter(client, api_key=api_key)
    ...
```

## 4. Set the environment variable

Add to your `.env` (never commit a real value):

```
ECHO_API_KEY=tutorial-value
```

## 5. Run it

Start the app and confirm the new model appears and parses:

```powershell
uv run --extra cpu streamlit run workspace_app.py --server.port=8551
```

1. Open [http://127.0.0.1:8551](http://127.0.0.1:8551).
2. On **Parse**, activate **Cloud AI ADE**.
3. Open the model dropdown — **you should now see "Echo (tutorial)"** alongside Grok 4.6,
   GPT-5.6 Luna, Gemini 3.5 Flash-Lite, Gemini 3.7 Flash, Claude Sonnet 5, and Agnes 2.5
   Flash.
4. Select it, upload any sample document, choose a page range, and select **Parse files**.
5. Confirm the parse completes and the Output tab shows a result (in this stub, the fixed
   "Echo stub output" text) rather than an error.

You've now added a fifth provider end to end: catalog entry, adapter module, contract
implementation, environment variable, and a live parse through the UI.

## Next steps

- Make the model actually call an endpoint — see
  [`docs/how-to/extend-a-provider.md`](../how-to/extend-a-provider.md) for narrower recipes
  once you have a real provider.
- Read [`docs/reference/provider-contract.md`](../reference/provider-contract.md) for the
  exact, exhaustive field list this stub only partially uses.
- Read [`docs/explanation/why-explicit-providers.md`](../explanation/why-explicit-providers.md)
  for why Paperplane is structured this way instead of using a shared base class or plugin
  registry.
