# How to extend an existing provider

Recipes for narrower changes to a provider that's already wired in. For adding a whole new
provider from scratch, see
[`docs/tutorials/add-a-provider.md`](../tutorials/add-a-provider.md). For the exact fields
referenced below, see [`docs/reference/provider-contract.md`](../reference/provider-contract.md).

## Add a new model to an existing provider

Google's catalog already has two entries (Gemini 3.5 Flash-Lite and Gemini 3.7 Flash) that
share one adapter module — this is the pattern to follow.

1. Add the model ID to the adapter's allowlist. For Gemini, that's `GEMINI_MODELS` at
   [`paperplane/gemini_document.py:24`](../../paperplane/gemini_document.py):

   ```python
   GEMINI_MODELS = {"gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-4.0-flash"}
   ```

2. If the new model needs different request-time handling (a different minimum thinking
   level, a different endpoint path), branch on `model` inside `generate_structured` the way
   the existing minimum-thinking-level check does:
   ([`paperplane/gemini_document.py:89-90`](../../paperplane/gemini_document.py)):

   ```python
   minimum_thinking_level = "minimal" if model == "gemini-3.5-flash-lite" else "low"
   ```

3. Append a new `DocumentModel` to `DOCUMENT_MODELS` in
   [`paperplane/model_catalog.py:33-101`](../../paperplane/model_catalog.py) with the same
   `provider="google"` and `api_key_env="GOOGLE_API_KEY"` as the existing Gemini entries —
   no adapter wiring in `runtime.py` is needed since the provider branch already exists.

4. Add the model to [`docs/MODELS.md`](../MODELS.md)'s catalog table (required by
   `CONTRIBUTING.md`'s documentation rule).

## Adjust quality-tier (Fast/Balanced/Audit) behavior

Quality-tier policy lives centrally in
[`paperplane/pipeline_contracts.py:45-79`](../../paperplane/pipeline_contracts.py) as
`ModePolicy` entries keyed by `ProcessingMode` (`ECONOMY`/`BALANCED`/`AUDIT`, which the UI
labels Fast/Balanced/Audit):

```python
_MODE_POLICIES = {
    ProcessingMode.ECONOMY: ModePolicy(
        base_dpi=150,
        crop_dpi=300,
        draft_reasoning_effort="none",
        verification_reasoning_effort=None,
        verification_scope="none",
        max_repair_rounds=1,
    ),
    ...
}
```

This is shared across every provider — you do not edit individual provider modules to
change DPI, reasoning effort, verification scope, or repair-round limits. To change how one
specific provider *responds* to a given mode (for example, a provider whose reasoning
parameter needs a non-default mapping at a given effort level), branch inside that
provider's `generate_structured`, the way Gemini maps `reasoning_effort="none"` to its
per-model minimum thinking level instead of a true "off"
([`paperplane/gemini_document.py:89-90`](../../paperplane/gemini_document.py)):

```python
thinking_level = minimum_thinking_level if reasoning_effort == "none" else reasoning_effort
```

Do not add a new `ProcessingMode` value unless you are changing the quality tiers offered
to every provider — that is a bigger change than adjusting one provider's behavior within
existing tiers.

## Swap or edit a prompt

Provider modules don't own their own prompts — `instructions` and `context` are passed in
by the caller (`pipeline.py`, see e.g. the figure-description call at
[`paperplane/pipeline.py:520-524`](../../paperplane/pipeline.py)) as parameters to
`generate_structured`. To change what's asked of a provider:

1. Find the call site in `pipeline.py` that builds the `instructions` string for the
   workflow you want to change (figure description, page draft, verification, repair).
2. Edit the instructions text there — not inside the provider module.
3. If the change should apply to only one provider, branch on the adapter type or a passed
   flag at the call site; do not special-case it inside a shared prompt-builder used by all
   providers.
4. If the provider needs the prompt delivered differently (e.g. as a separate `system`
   field instead of concatenated into `instructions`), that reshaping happens inside the
   provider module's `generate_structured`, using the same `instructions`/`context`
   parameters it already receives — the external contract does not change.

## Change a provider's error handling

Every provider module defines its own error subclass inheriting from `OpenAIRequestError`
(e.g. `GeminiRequestError` — [`paperplane/gemini_document.py:27-28`](../../paperplane/gemini_document.py)).
To add a new failure case (say, a provider-specific rate-limit response):

1. Catch the new failure inside `generate_structured`, alongside the existing
   `except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError, TypeError)` clause
   ([`paperplane/gemini_document.py:118`](../../paperplane/gemini_document.py)).
2. Call `_emit_audit` with `"status": "error"` and a descriptive `"error_type"` before
   raising, so the failure is traceable.
3. Raise the module's own error subclass — never a bare exception — so
   `runtime.py`'s shared `except (DocumentInputError, OpenAIRequestError, ...)` clause
   ([`paperplane/runtime.py:223`](../../paperplane/runtime.py)) still isolates the failure
   to one file in the batch.

## Related pages

- [Reference: provider contract](../reference/provider-contract.md)
- [Tutorial: add a provider](../tutorials/add-a-provider.md)
- [Explanation: why explicit providers](../explanation/why-explicit-providers.md)
