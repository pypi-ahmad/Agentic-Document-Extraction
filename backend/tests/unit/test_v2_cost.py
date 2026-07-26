from app.services.parsing.openai_document import OpenAIUsage
from app.services.parsing.v2_cost import ModelRates, calculate_usage_cost


def test_cost_accounts_for_cache_reads_and_billable_cache_writes() -> None:
    result = calculate_usage_cost(
        {
            "gpt-5.6-luna": OpenAIUsage(
                input_tokens=2_000,
                output_tokens=100,
                cached_input_tokens=1_000,
                cache_write_tokens=500,
            )
        },
        {
            "gpt-5.6-luna": ModelRates(
                input_per_million=1.0,
                cached_input_per_million=0.1,
                output_per_million=5.0,
            )
        },
    )

    # 500 uncached + 1000 cached + 500 cache-write at 1.25x + 100 output.
    assert result.total_usd == 0.001725
    assert result.by_model["gpt-5.6-luna"] == 0.001725
