# Provider contract reference

This page describes exactly what a cloud AI provider module and its `model_catalog.py`
entry must expose. It is a dictionary, not a walkthrough — see
[`docs/tutorials/add-a-provider.md`](../tutorials/add-a-provider.md) for a worked example.

## Catalog entry: `DocumentModel`

Defined in [`paperplane/model_catalog.py:12-23`](../../paperplane/model_catalog.py). One
`DocumentModel` instance describes each entry in `DOCUMENT_MODELS`
([`paperplane/model_catalog.py:33-101`](../../paperplane/model_catalog.py)).

| Field | Type | Required | Notes |
|---|---|---|---|
| `label` | `str` | yes | Display name shown in the Streamlit model picker. |
| `model_id` | `str` | yes | API identifier passed to the provider adapter and used as the dict key in `DOCUMENT_MODEL_BY_ID`. |
| `provider` | `Provider` | yes | One of `"xai" \| "openai" \| "google" \| "anthropic" \| "agnes"` ([`paperplane/model_catalog.py:9`](../../paperplane/model_catalog.py)). Selects the adapter class in `runtime.py`. |
| `api_key_env` | `str` | yes | Name of the environment variable holding the credential. Never the credential value itself. |
| `help_text` | `str` | yes | One sentence shown in the UI. |
| `docs_url` | `str` | yes | Link to the provider's own model documentation. |
| `input_price_per_million` | `Decimal` | yes | USD per 1M input tokens, for the Cost page estimate. |
| `output_price_per_million` | `Decimal` | yes | USD per 1M output tokens. |
| `cached_input_price_per_million` | `Decimal \| None` | no | Only if the provider bills cached input separately (see GPT-5.6 Luna). |
| `pricing_note` | `str` | no | One line documenting what the configured rate does *not* cover (batch discounts, surcharges, etc.). |

Adding an entry requires updating three places that read `DOCUMENT_MODELS`:
`DOCUMENT_MODEL_BY_ID`, `DOCUMENT_MODEL_BY_LABEL`
([`paperplane/model_catalog.py:104-105`](../../paperplane/model_catalog.py)) are built
automatically from the tuple, so appending one `DocumentModel` is sufficient — no other
catalog-side registration exists.

## Adapter class: the `StructuredAdapter` protocol

Every provider module exposes one adapter class matching the structural `StructuredAdapter`
protocol defined at [`paperplane/pipeline.py:172-185`](../../paperplane/pipeline.py):

```python
class StructuredAdapter(Protocol):
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
    ) -> StructuredGeneration: ...
```

There is no shared base class — this is Python structural typing (`Protocol`). A provider
module satisfies the contract by implementing a class with a matching
`generate_structured` method; it does not need to inherit from anything.

### Constructor

Every existing adapter accepts an `httpx.AsyncClient` positionally and `api_key` as a
keyword-only argument, e.g.
[`paperplane/gemini_document.py:32-41`](../../paperplane/gemini_document.py):

```python
def __init__(
    self,
    http: httpx.AsyncClient,
    *,
    api_key: str,
    base_url: str = DEFAULT_GEMINI_BASE_URL,
) -> None: ...
```

`runtime.py`'s `cloud_adapter()` helper
([`paperplane/runtime.py:108-125`](../../paperplane/runtime.py)) constructs each adapter
with exactly this shape — one `if provider == "..."` branch per provider, calling
`AdapterClass(client, api_key=api_key)` (or with an extra `base_url=`/`provider_name=`
keyword, as xAI does by reusing `OpenAIDocumentAdapter` with a different base URL).

### `generate_structured` parameters

| Parameter | Type | Meaning |
|---|---|---|
| `model` | `str` | The `model_id` from the catalog entry. Adapters typically validate it against a hardcoded allowlist, e.g. `GEMINI_MODELS` at [`paperplane/gemini_document.py:24`](../../paperplane/gemini_document.py). |
| `image` | `bytes \| None` | PNG bytes of the page/crop being sent, or `None` for text-only calls. |
| `instructions` | `str` | The prompt body. |
| `context` | `str \| None` | Optional prior-page Markdown context, appended to instructions. |
| `schema_name` | `str` | Identifies the JSON schema being requested, for audit logging. |
| `schema` | `dict[str, Any]` | A JSON Schema describing the required structured output shape. |
| `reasoning_effort` | `Literal["none", "low", "medium", "high"]` | Maps to the provider's own thinking/reasoning parameter. Gemini maps `"none"` to its per-model minimum thinking level ([`paperplane/gemini_document.py:89-90`](../../paperplane/gemini_document.py)) rather than disabling it, since Gemini has no true "off". |
| `detail` | `Literal["low", "high", "original"]` | Image detail/resolution hint. Adapters that don't support this (Gemini) discard it explicitly with `del detail` ([`paperplane/gemini_document.py:56`](../../paperplane/gemini_document.py)) rather than silently ignoring an unused parameter. |
| `prompt_cache_key` | `str` | Passed through for providers with explicit prompt-caching support; unused otherwise. |

### Return value: `StructuredGeneration`

Defined in [`paperplane/openai_document.py:51-59`](../../paperplane/openai_document.py) and
re-exported/reused by every other provider module:

| Field | Type | Notes |
|---|---|---|
| `response_id` | `str \| None` | Provider's own response/request ID, for audit trails. |
| `value` | `dict[str, Any]` | The parsed JSON object matching `schema`. Must be a `dict` — adapters raise their own request-error subclass if the provider returns anything else (e.g. [`paperplane/gemini_document.py:129-131`](../../paperplane/gemini_document.py)). |
| `usage` | `OpenAIUsage` | Token usage — see below. Field name is historical (`OpenAIUsage`), reused by all providers. |
| `model_usage` | `dict[str, OpenAIUsage]` | Only populated by chained/hybrid adapters that call more than one model. |
| `latency_ms` | `float` (`>= 0`) | Wall-clock request latency. |
| `presegmented` | `bool` | Whether the provider returned page regions already segmented (default `False`). |
| `warnings` | `list[str]` | Non-fatal issues to surface in the UI. |

`OpenAIUsage` ([`paperplane/openai_document.py:44-48`](../../paperplane/openai_document.py)):
`input_tokens`, `output_tokens`, `cached_input_tokens`, `cache_write_tokens` — all
`int`, default `0`, `ge=0`.

### Error handling

Each module defines its own request-error subclass inheriting from
`OpenAIRequestError` (e.g. `GeminiRequestError` at
[`paperplane/gemini_document.py:27-28`](../../paperplane/gemini_document.py)). Adapters
must raise this (not a bare exception) on:

- a missing/empty API key,
- an unsupported `model` value,
- a transport, HTTP, or JSON-decode failure,
- a structured response that isn't a JSON object.

`runtime.py` catches `OpenAIRequestError` (and its subclasses, since they all inherit from
it) alongside `DocumentInputError`, `OllamaRequestError`, and `ValueError`
([`paperplane/runtime.py:223`](../../paperplane/runtime.py)) to isolate one failed file
from the rest of a batch.

### Audit logging

Call `_emit_audit(record)` (imported from `openai_document`, e.g.
[`paperplane/gemini_document.py:19`](../../paperplane/gemini_document.py)) once on error and
once on success, with a `dict` documenting at minimum: `model`, `schema_name`,
`schema_sha256`, `instructions`, `context`, `reasoning_effort`, `prompt_cache_key`, an
`image_sha256` (never the raw image), and a `status` of `"error"` or `"completed"`. This is
what makes provider calls traceable without ever logging credentials or full document
content.

## Related pages

- [Tutorial: add a provider](../tutorials/add-a-provider.md)
- [How-to: extend a provider](../how-to/extend-a-provider.md)
- [Explanation: why explicit providers](../explanation/why-explicit-providers.md)
- [`docs/MODELS.md`](../MODELS.md) — the user-facing catalog table
