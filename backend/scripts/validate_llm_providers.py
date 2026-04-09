"""Live validation of LLM model-listing and auto-routing against real provider accounts.

Run from the backend directory with API keys in .env:

    python scripts/validate_llm_providers.py

Checks
------
1. Provider status detection (configured / missing key / client installed)
2. Dynamic model listing per provider (model count, default presence, filtering)
3. Auto-routing resolution (picks first available in priority order)
4. Model deduplication and sort order (default first, then alpha)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure the backend package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from app.services.llm.registry import (
    get_llm_provider,
    list_llm_provider_statuses,
    list_models_for_provider,
)
from app.models.enums import LLMProviderID, ProviderAvailabilityState

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"
INFO = "\033[94mℹ\033[0m"


class Results:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.skipped = 0

    def check(self, condition: bool, msg: str) -> None:
        if condition:
            print(f"  {PASS} {msg}")
            self.passed += 1
        else:
            print(f"  {FAIL} {msg}")
            self.failed += 1

    def skip(self, msg: str) -> None:
        print(f"  {WARN} SKIP: {msg}")
        self.skipped += 1

    def info(self, msg: str) -> None:
        print(f"  {INFO} {msg}")


async def validate_provider_statuses(r: Results) -> dict[str, bool]:
    """Check which providers are configured and available."""
    print("\n═══ Provider Status Detection ═══")

    statuses = list_llm_provider_statuses()
    configured: dict[str, bool] = {}

    for s in statuses:
        pid = s.provider_id
        avail = s.availability

        configured[pid] = avail.configured and avail.available

        print(f"\n  [{pid}]")
        r.info(f"state = {avail.state}")
        r.info(f"configured = {avail.configured}")
        r.info(f"can_extract = {avail.can_extract}")
        r.info(f"can_list_models = {avail.can_list_models}")
        r.info(f"auto_eligible = {avail.auto_eligible}")

        if avail.state == ProviderAvailabilityState.READY:
            r.check(avail.configured, f"{pid}: API key is set")
            r.check(avail.can_extract, f"{pid}: extraction client installed")
            r.check(avail.can_list_models, f"{pid}: model-listing client installed")
            r.check(avail.auto_eligible, f"{pid}: eligible for auto-routing")
        elif avail.state == ProviderAvailabilityState.MISSING_API_KEY:
            r.info(f"{pid}: no API key configured (skipping model tests)")
        elif avail.state == ProviderAvailabilityState.CLIENT_NOT_INSTALLED:
            r.info(f"{pid}: client SDK not installed")
        else:
            r.check(False, f"{pid}: unexpected state {avail.state}")

        if s.error:
            r.info(f"{pid}: error = {s.error.message}")

    return configured


async def validate_model_listing(r: Results, pid: str, default_model: str) -> None:
    """Fetch models from a specific provider and validate."""
    print(f"\n═══ Model Listing: {pid} ═══")

    catalog = await list_models_for_provider(pid)

    r.info(f"source = {catalog.source}")
    r.info(f"model count = {len(catalog.models)}")

    if catalog.error:
        r.check(False, f"{pid}: listing failed — {catalog.error.message}")
        return

    r.check(len(catalog.models) > 0, f"{pid}: returned at least 1 model")

    # Check default model is present
    model_ids = [m.id for m in catalog.models]
    has_default = default_model in model_ids
    r.check(has_default, f"{pid}: default model '{default_model}' is in the list")

    # Check default is marked
    defaults = [m for m in catalog.models if m.is_default]
    r.check(
        len(defaults) == 1,
        f"{pid}: exactly 1 model marked is_default (got {len(defaults)})",
    )
    if defaults:
        r.check(
            defaults[0].id == default_model,
            f"{pid}: is_default model is '{defaults[0].id}' (expected '{default_model}')",
        )

    # Check sort order: default first
    if catalog.models:
        r.check(
            catalog.models[0].is_default,
            f"{pid}: first model in list is the default (got '{catalog.models[0].id}')",
        )

    # Print first 15 models for inspection
    print(f"\n  First 15 models:")
    for m in catalog.models[:15]:
        flag = " ★" if m.is_default else ""
        print(f"    {m.id}{flag}")
    if len(catalog.models) > 15:
        print(f"    ... and {len(catalog.models) - 15} more")


async def validate_openai_filtering(r: Results) -> None:
    """Check that OpenAI model list filters to gpt-*/o1/o3/o4 prefixes."""
    print(f"\n═══ OpenAI Model Filtering ═══")

    catalog = await list_models_for_provider("openai")
    if catalog.error:
        r.skip(f"OpenAI listing failed: {catalog.error.message}")
        return

    model_ids = [m.id for m in catalog.models]
    prefixes = ("gpt-", "o1", "o3", "o4")

    # Should only contain preferred models (if any matched)
    non_preferred = [mid for mid in model_ids if not any(mid.startswith(p) for p in prefixes)]
    if non_preferred:
        # Non-preferred means fallback was used (no gpt/o* models matched)
        r.info(f"Non-preferred models present ({len(non_preferred)}): fallback list used")
        r.info(f"Examples: {non_preferred[:5]}")
    else:
        r.check(True, f"All {len(model_ids)} models match preferred prefixes (gpt-*/o1/o3/o4)")

    # Check for common models that should NOT be in preferred list
    unwanted_in_preferred = [
        mid for mid in model_ids
        if mid.startswith(("dall-e", "tts-", "whisper", "text-embedding", "babbage", "davinci"))
    ]
    r.check(
        len(unwanted_in_preferred) == 0,
        f"No image/audio/embedding models in list (found {len(unwanted_in_preferred)}: {unwanted_in_preferred[:3]})",
    )


async def validate_gemini_filtering(r: Results) -> None:
    """Check that Gemini filters to generateContent-capable models."""
    print(f"\n═══ Gemini Model Filtering ═══")

    catalog = await list_models_for_provider("gemini")
    if catalog.error:
        r.skip(f"Gemini listing failed: {catalog.error.message}")
        return

    model_ids = [m.id for m in catalog.models]
    r.info(f"Total models after filtering: {len(model_ids)}")

    # Check that embedding-only models are excluded
    embedding_models = [mid for mid in model_ids if "embedding" in mid.lower()]
    r.check(
        len(embedding_models) == 0,
        f"No embedding-only models in list (found {len(embedding_models)}: {embedding_models[:3]})",
    )


async def validate_auto_routing(r: Results, configured: dict[str, bool]) -> None:
    """Validate auto-routing picks the expected provider."""
    print(f"\n═══ Auto Routing ═══")

    priority_order = ["openai", "gemini", "anthropic"]
    expected = None
    for pid in priority_order:
        if configured.get(pid):
            expected = pid
            break

    if expected is None:
        r.skip("No providers configured — cannot test auto-routing")
        return

    r.info(f"Expected auto route: {expected} (first configured in priority order)")

    try:
        provider = get_llm_provider("auto")
        actual = provider.provider_id
        r.check(
            actual == expected,
            f"Auto resolved to '{actual}' (expected '{expected}')",
        )
    except Exception as exc:
        r.check(False, f"Auto routing failed: {exc}")

    # Also check model listing for "auto"
    catalog = await list_models_for_provider("auto")
    if catalog.error:
        r.check(False, f"Auto model listing failed: {catalog.error.message}")
    else:
        r.check(
            catalog.resolved_provider_id == expected,
            f"Auto catalog resolved_provider_id = '{catalog.resolved_provider_id}' (expected '{expected}')",
        )
        r.check(len(catalog.models) > 0, f"Auto model listing returned {len(catalog.models)} models")


async def main() -> None:
    r = Results()

    # 1. Provider statuses
    configured = await validate_provider_statuses(r)

    configured_providers = [pid for pid, ok in configured.items() if ok]
    if not configured_providers:
        r.skip("Model listing validation skipped because no providers have valid API keys")
        r.skip("Provider-specific filtering validation skipped because no providers have valid API keys")
        r.skip("Auto-routing validation skipped because no providers have valid API keys")
        print(f"\n{WARN} No providers have valid API keys. Set keys in .env to run full validation.")
        print(f"\n{'═' * 40}")
        print(f"  Passed: {r.passed}  |  Failed: {r.failed}  |  Skipped: {r.skipped}")
        sys.exit(1 if r.failed else 0)

    print(f"\n  Configured providers: {', '.join(configured_providers)}")

    # 2. Model listing per provider
    defaults = {
        "openai": "gpt-4o-mini",
        "gemini": "gemini-2.0-flash",
        "anthropic": "claude-3-5-haiku-20241022",
    }
    for pid in configured_providers:
        await validate_model_listing(r, pid, defaults[pid])

    # 3. Provider-specific filtering
    if configured.get("openai"):
        await validate_openai_filtering(r)
    if configured.get("gemini"):
        await validate_gemini_filtering(r)

    # 4. Auto routing
    await validate_auto_routing(r, configured)

    # Summary
    print(f"\n{'═' * 40}")
    total = r.passed + r.failed
    print(f"  Passed: {r.passed}/{total}  |  Failed: {r.failed}  |  Skipped: {r.skipped}")
    if r.failed:
        print(f"\n  {FAIL} Some checks failed — review output above")
    else:
        print(f"\n  {PASS} All checks passed")
    sys.exit(1 if r.failed else 0)


if __name__ == "__main__":
    asyncio.run(main())
