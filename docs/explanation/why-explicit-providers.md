# Why explicit providers, not a plugin registry

Paperplane has one Python module per cloud provider — `openai_document.py`,
`gemini_document.py`, `anthropic_document.py`, `agnes_document.py`, `ollama_document.py` —
each implementing the same structural `StructuredAdapter` protocol
([`paperplane/pipeline.py:172-185`](../../paperplane/pipeline.py)), wired together by a
plain `if provider == "..."` chain in `runtime.py`'s `cloud_adapter()` helper
([`paperplane/runtime.py:108-125`](../../paperplane/runtime.py)). There is no shared base
class, no plugin discovery mechanism, and no runtime provider registration. This is a
deliberate choice, not an oversight.

## No shared base class

A `Protocol` (structural typing), not an abstract base class, defines the contract. Every
adapter independently implements `generate_structured` with the same signature, but nothing
forces them to share implementation. `GeminiDocumentAdapter` reuses `OpenAIRequestError`,
`OpenAIUsage`, `StructuredGeneration`, and `_emit_audit` from `openai_document.py`
([`paperplane/gemini_document.py:14-19`](../../paperplane/gemini_document.py)) by direct
import — convenience, not inheritance.

Providers genuinely differ in how they need to behave, and every existing provider bears
that out:

- Gemini has no true "reasoning off" — `reasoning_effort="none"` maps to a per-model
  minimum thinking level instead of a boolean toggle
  ([`paperplane/gemini_document.py:89-90`](../../paperplane/gemini_document.py)).
- Gemini also ignores the `detail` (image resolution) parameter entirely, discarding it
  with an explicit `del detail`
  ([`paperplane/gemini_document.py:56`](../../paperplane/gemini_document.py)) rather than
  a shared base class silently no-op'ing it.
- xAI reuses the OpenAI-shaped adapter with different constructor flags
  (`provider_name="xAI"`, `explicit_prompt_cache=False`, `image_detail=False`,
  `minimum_reasoning_effort="low"` —
  [`paperplane/runtime.py:116-124`](../../paperplane/runtime.py)) instead of a fifth module,
  because its request shape genuinely is the OpenAI shape with different defaults.
- Ollama's adapter can be composed into a `ChainedStructuredAdapter` that runs a local model
  first and a cloud model second ([`paperplane/runtime.py:136-139`](../../paperplane/runtime.py)),
  a composition a common base class would have to special-case rather than express plainly.

A shared base class would have to grow enough hooks and overrides to cover all four
divergences above before a fifth provider ships — at which point it's an abstraction
maintained for its own sake, not because two providers actually share behavior. Duplicating
the visible parts of `generate_structured` (three or four modules currently do) and sharing
only the genuinely reusable pieces (`OpenAIUsage`, `StructuredGeneration`, `_emit_audit`) by
import is a smaller, more honest surface than a framework built to anticipate providers that
don't exist yet.

## No plugin registry or auto-discovery

Adding a provider means editing two files by hand: `model_catalog.py` (the entry) and
`runtime.py` (one `if` branch in `cloud_adapter()`). There is no `entry_points`, no
directory-scan-and-import, no decorator-based registration. This matches the same
philosophy stated for engine selection in the project's [README](../../README.md) and
[`docs/ENGINES.md`](../ENGINES.md): **Paperplane never auto-routes.** A batch's engine is
always one of four explicit toggles the user picked; a parse's provider is always one of
the six catalog entries the user selected from a dropdown, constructed by one visible line
of code the maintainer wrote. Nothing decides which provider runs by scanning what's
installed or configured — traceability from "which provider ran" back to "which line of
code constructed it" is preserved by keeping that line manually written and centrally
visible, not distributed across auto-discovered plugin files.

## The cost of this choice

This is a real tradeoff, not a free lunch:

- Adding a provider touches two files instead of dropping in one self-contained plugin
  file. [`docs/tutorials/add-a-provider.md`](../tutorials/add-a-provider.md) shows this is
  still a five-step, single-sitting change — the cost is small in practice because the
  catalog and the `if` chain are both short, flat, and adjacent to each other.
- There's some duplication across provider modules (each defines its own request-error
  subclass, its own audit-record shape) rather than one enforced shape. In exchange, no
  provider module is constrained by assumptions baked in for a different provider.

## What this is not

This is not a claim that plugin architectures are wrong in general — it's a claim that six
providers with genuinely divergent request shapes, added a few times a year by the
maintainer, don't have the shared behavior or the growth rate that would make a registry
pay for itself. If Paperplane later supported dozens of interchangeable providers with
identical request shapes, revisiting this would be reasonable. That is not the situation
today.

## Related pages

- [Reference: provider contract](../reference/provider-contract.md)
- [Tutorial: add a provider](../tutorials/add-a-provider.md)
- [How-to: extend a provider](../how-to/extend-a-provider.md)
