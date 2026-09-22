# Why explicit providers, not a plugin registry

Paperplane has one Python module per cloud provider: `openai_document.py`,
`gemini_document.py`, `anthropic_document.py`, `agnes_document.py`, and `ollama_document.py`.
Each implements the same structural `StructuredAdapter` protocol
([`paperplane/pipeline.py:172-185`](../../paperplane/pipeline.py)), wired together by a
plain `if provider == "..."` chain in `runtime.py`'s `cloud_adapter()` helper
([`paperplane/runtime.py:108-125`](../../paperplane/runtime.py)). There is no shared base
class, plugin discovery mechanism, or runtime provider registration. The project keeps this
structure deliberately.

## No shared base class

A `Protocol` (structural typing) defines the contract. Every adapter independently implements
`generate_structured` with the same signature. `GeminiDocumentAdapter` reuses `OpenAIRequestError`,
`OpenAIUsage`, `StructuredGeneration`, and `_emit_audit` from `openai_document.py`
([`paperplane/gemini_document.py:14-19`](../../paperplane/gemini_document.py)) by direct
import. This reuses shared types without inheritance.

Each provider has different request behavior:

- Gemini has no true "reasoning off". `reasoning_effort="none"` maps to a per-model minimum
  thinking level instead of a boolean toggle
  ([`paperplane/gemini_document.py:89-90`](../../paperplane/gemini_document.py)).
- Gemini also ignores the `detail` (image resolution) parameter entirely, discarding it
  with an explicit `del detail`
  ([`paperplane/gemini_document.py:56`](../../paperplane/gemini_document.py)).
- xAI reuses the OpenAI-shaped adapter with different constructor flags
  (`provider_name="xAI"`, `explicit_prompt_cache=False`, `image_detail=False`,
  `minimum_reasoning_effort="low"`
  ([`paperplane/runtime.py:116-124`](../../paperplane/runtime.py)). Its request shape uses the
  OpenAI format with different defaults.
- Ollama's adapter can be composed into a `ChainedStructuredAdapter` that runs a local model
  first and a cloud model second ([`paperplane/runtime.py:136-139`](../../paperplane/runtime.py)).
  A common base class would need a special case for that composition.

A shared base class would need hooks and overrides for all four cases before a fifth provider
arrives. Three or four modules duplicate parts of `generate_structured` and import the shared
pieces: `OpenAIUsage`, `StructuredGeneration`, and `_emit_audit`. That keeps the shared surface
limited to behavior the adapters already have in common.

## No plugin registry or auto-discovery

Adding a provider means editing two files by hand: `model_catalog.py` (the entry) and
`runtime.py` (one `if` branch in `cloud_adapter()`). There is no `entry_points`, no
directory-scan-and-import, no decorator-based registration. This matches the same
philosophy stated for engine selection in the project's [README](../../README.md) and
[`docs/ENGINES.md`](../ENGINES.md): **Paperplane never auto-routes.** A batch's engine is
always one of four explicit toggles the user picked; a parse's provider is always one of
the six catalog entries the user selected from a dropdown, constructed by one visible line
of code the maintainer wrote. Nothing decides which provider runs by scanning what's
installed or configured. The explicit branch shows which line constructs the provider used for a
parse.

## The cost of this choice

This has costs:

- Adding a provider touches two files instead of dropping in one self-contained plugin
  file. [`docs/tutorials/add-a-provider.md`](../tutorials/add-a-provider.md) shows this is
  still a five-step change. The catalog and the `if` chain are short and adjacent to each other.
- There's some duplication across provider modules (each defines its own request-error
  subclass, its own audit-record shape) rather than one enforced shape. In exchange, no
  provider module is constrained by assumptions baked in for a different provider.

## Scope

This design fits six providers with different request shapes that the maintainer adds only a
few times a year. A registry may suit dozens of interchangeable providers with identical
request shapes.

## Related pages

- [Reference: provider contract](../reference/provider-contract.md)
- [Tutorial: add a provider](../tutorials/add-a-provider.md)
- [How-to: extend a provider](../how-to/extend-a-provider.md)
