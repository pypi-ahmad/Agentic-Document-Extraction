"""Current-session token usage and estimated provider cost."""

from __future__ import annotations

from decimal import Decimal

import streamlit as st

from paperplane.contracts import ModelTokenUsage
from paperplane.model_catalog import DOCUMENT_MODEL_BY_ID, estimate_model_cost


def format_cost(value: Decimal) -> str:
    return f"${value:.6f}" if value < 1 else f"${value:.4f}"


def aggregate_session_usage() -> dict[str, ModelTokenUsage]:
    aggregate: dict[str, ModelTokenUsage] = {}
    for parse_usage in st.session_state.get("session_usage", {}).values():
        for model_id, raw_usage in parse_usage.items():
            usage = ModelTokenUsage.model_validate(raw_usage)
            total = aggregate.setdefault(model_id, ModelTokenUsage())
            total.input_tokens += usage.input_tokens
            total.output_tokens += usage.output_tokens
            total.cached_input_tokens += usage.cached_input_tokens
            total.cache_write_tokens += usage.cache_write_tokens
    return aggregate


def estimated_cost(model_id: str, usage: ModelTokenUsage) -> Decimal:
    if model_id not in DOCUMENT_MODEL_BY_ID:
        return Decimal("0")
    return estimate_model_cost(
        model_id,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_input_tokens=usage.cached_input_tokens,
    ).total_cost_usd


st.title("Cost")
st.caption(
    "Provider-reported token usage accumulated in this browser session. "
    "New parse does not reset these totals."
)

usage_by_model = aggregate_session_usage()
total_input = sum(usage.input_tokens for usage in usage_by_model.values())
total_cached = sum(usage.cached_input_tokens for usage in usage_by_model.values())
total_output = sum(usage.output_tokens for usage in usage_by_model.values())
total_cost = sum(
    (estimated_cost(model_id, usage) for model_id, usage in usage_by_model.items()),
    start=Decimal("0"),
)

with st.container(horizontal=True):
    st.metric("Input tokens", f"{total_input:,}", border=True)
    st.metric("Cache tokens", f"{total_cached:,}", border=True)
    st.metric("Output tokens", f"{total_output:,}", border=True)
    st.metric("Estimated cost", format_cost(total_cost), border=True)

if not usage_by_model:
    st.info("No successful model usage has been recorded in this session.")
else:
    rows: list[dict[str, str | int]] = []
    for model_id, usage in sorted(
        usage_by_model.items(),
        key=lambda item: (
            DOCUMENT_MODEL_BY_ID[item[0]].label if item[0] in DOCUMENT_MODEL_BY_ID else item[0]
        ),
    ):
        model = DOCUMENT_MODEL_BY_ID.get(model_id)
        rows.append(
            {
                "Model": model.label if model is not None else model_id,
                "Input tokens": usage.input_tokens,
                "Cache tokens": usage.cached_input_tokens,
                "Output tokens": usage.output_tokens,
                "Estimated cost": format_cost(estimated_cost(model_id, usage)),
            }
        )
    rows.append(
        {
            "Model": "Total",
            "Input tokens": total_input,
            "Cache tokens": total_cached,
            "Output tokens": total_output,
            "Estimated cost": format_cost(total_cost),
        }
    )
    st.dataframe(rows, hide_index=True)

st.caption(
    "Free and local models contribute token counts but $0 API cost. Estimates use the "
    "configured synchronous rates; failed requests without usage metadata are not included."
)
