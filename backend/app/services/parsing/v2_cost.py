"""Versionable OpenAI token pricing calculations for UI cost reporting."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.parsing.openai_document import OpenAIUsage


class ModelRates(BaseModel):
    input_per_million: float = Field(ge=0)
    cached_input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)


class UsageCost(BaseModel):
    total_usd: float
    by_model: dict[str, float]


def calculate_usage_cost(
    usage_by_model: dict[str, OpenAIUsage], rates: dict[str, ModelRates]
) -> UsageCost:
    by_model: dict[str, float] = {}
    for model, usage in usage_by_model.items():
        model_rates = rates.get(model)
        if model_rates is None:
            continue
        uncached = max(0, usage.input_tokens - usage.cached_input_tokens - usage.cache_write_tokens)
        cost = (
            uncached * model_rates.input_per_million
            + usage.cached_input_tokens * model_rates.cached_input_per_million
            + usage.cache_write_tokens * model_rates.input_per_million * 1.25
            + usage.output_tokens * model_rates.output_per_million
        ) / 1_000_000
        by_model[model] = round(cost, 9)
    return UsageCost(total_usd=round(sum(by_model.values()), 9), by_model=by_model)
