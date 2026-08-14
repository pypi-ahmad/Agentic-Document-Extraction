from decimal import Decimal

from paperplane.model_catalog import (
    DOCUMENT_MODEL_BY_ID,
    DOCUMENT_MODELS,
    estimate_model_cost,
)


def test_document_model_catalog_uses_only_verified_api_ids() -> None:
    assert [model.model_id for model in DOCUMENT_MODELS] == [
        "grok-4.6",
        "gpt-5.6-luna",
        "gemini-3.5-flash-lite",
        "gemini-3.6-flash",
        "claude-sonnet-5",
        "agnes-2.5-flash",
    ]


def test_document_model_catalog_maps_provider_credentials() -> None:
    assert {model.api_key_env for model in DOCUMENT_MODELS} == {
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_API_KEY",
        "ANTHROPIC_API_KEY",
        "AGNES_API_KEY",
    }


def test_cost_estimate_applies_luna_cached_input_rate() -> None:
    estimate = estimate_model_cost(
        "gpt-5.6-luna",
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=1_000_000,
    )

    assert estimate.input_cost_usd == Decimal("0.155")
    assert estimate.output_cost_usd == Decimal("1.20")
    assert estimate.total_cost_usd == Decimal("1.355")


def test_agnes_cost_estimate_is_free() -> None:
    estimate = estimate_model_cost(
        "agnes-2.5-flash",
        input_tokens=2_000_000,
        output_tokens=1_000_000,
    )

    assert estimate.total_cost_usd == 0


def test_gemini_36_rate_is_derived_from_supplied_promo_comparison() -> None:
    model = DOCUMENT_MODEL_BY_ID["gemini-3.6-flash"]

    assert model.input_price_per_million == Decimal("1.50")
    assert model.output_price_per_million == Decimal("7.50")
