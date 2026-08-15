from decimal import Decimal

import pytest

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
        "gemini-3.7-flash",
        "claude-sonnet-5",
        "agnes-2.5-flash",
    ]


def test_document_model_catalog_maps_provider_credentials() -> None:
    assert {model.api_key_env for model in DOCUMENT_MODELS} == {
        "XAI_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "ANTHROPIC_API_KEY",
        "AGNES_API_KEY",
    }


@pytest.mark.parametrize(
    ("model_id", "input_rate", "output_rate"),
    [
        ("claude-sonnet-5", "2.00", "10.00"),
        ("gemini-3.7-flash", "0.75", "3.75"),
        ("gemini-3.5-flash-lite", "0.30", "2.50"),
        ("gpt-5.6-luna", "0.20", "1.20"),
        ("grok-4.6", "2.00", "6.00"),
        ("agnes-2.5-flash", "0", "0"),
    ],
)
def test_document_model_catalog_uses_supplied_standard_rates(
    model_id: str, input_rate: str, output_rate: str
) -> None:
    model = DOCUMENT_MODEL_BY_ID[model_id]

    assert model.input_price_per_million == Decimal(input_rate)
    assert model.output_price_per_million == Decimal(output_rate)


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


def test_gemini_37_uses_supplied_promotional_rate() -> None:
    model = DOCUMENT_MODEL_BY_ID["gemini-3.7-flash"]

    assert model.input_price_per_million == Decimal("0.75")
    assert model.output_price_per_million == Decimal("3.75")
