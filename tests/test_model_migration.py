"""Request, billing, and UI regression checks for the GPT-6 Sol migration."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from paperplane.model_catalog import DEFAULT_DOCUMENT_MODEL, DOCUMENT_MODELS, estimate_model_cost
from paperplane.openai_document import OpenAIDocumentAdapter, capture_audit_calls


@pytest.mark.parametrize("requested_effort", ["none", "low", "medium", "high"])
async def test_sol_requests_and_audits_use_medium(requested_effort):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "test-response",
                "output": [{"content": [{"type": "output_text", "text": '{"text":"42"}'}]}],
                "usage": {
                    "input_tokens": 1000,
                    "output_tokens": 100,
                    "input_tokens_details": {"cached_tokens": 200, "cache_write_tokens": 300},
                },
            },
        )

    records = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(client, api_key="test-only")
        with capture_audit_calls(records):
            generation = await adapter.generate_structured(
                model=DEFAULT_DOCUMENT_MODEL,
                image=b"synthetic-image",
                instructions="Read the number.",
                schema_name="read_number",
                schema={"type": "object"},
                reasoning_effort=requested_effort,
                detail="high",
                prompt_cache_key="test",
            )
    payload = requests[0]
    assert payload["model"] == "gpt-6-sol"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["store"] is False
    assert payload["text"]["format"]["strict"] is True
    assert payload["prompt_cache_options"] == {"mode": "explicit", "ttl": "30m"}
    assert payload["input"][0]["content"][1]["type"] == "input_image"
    assert records[0]["reasoning_effort"] == "medium"
    assert generation.usage.cache_write_tokens == 300
    assert estimate_model_cost(
        DEFAULT_DOCUMENT_MODEL, **generation.usage.model_dump()
    ).total_cost_usd == Decimal("0.00279")


@pytest.mark.parametrize("requested,expected", [("none", "low"), ("high", "high")])
async def test_xai_keeps_its_reasoning_and_cache_behavior(requested, expected):
    def respond(request):
        payload = json.loads(request.content)
        assert payload["reasoning"] == {"effort": expected}
        assert "prompt_cache_options" not in payload
        assert "prompt_cache_breakpoint" not in payload["input"][0]["content"][0]
        return httpx.Response(
            200, json={"output": [{"content": [{"type": "output_text", "text": "{}"}]}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        adapter = OpenAIDocumentAdapter(
            client,
            api_key="test-only",
            provider_name="xAI",
            explicit_prompt_cache=False,
            minimum_reasoning_effort="low",
        )
        await adapter.generate_structured(
            model="grok-4.6",
            image=None,
            instructions="Read.",
            schema_name="test",
            schema={"type": "object"},
            reasoning_effort=requested,
            detail="high",
            prompt_cache_key="test",
        )


@pytest.mark.parametrize(
    "input_tokens,cached,written,output_tokens,expected",
    [
        (1000, 0, 0, 100, "0.003"),
        (1000, 1000, 0, 0, "0.0002"),
        (1000, 0, 1000, 0, "0.0025"),
        (1000, 200, 300, 100, "0.00279"),
        (0, 0, 0, 0, "0"),
        (-1, -2, -3, -4, "0"),
        (1000, 1200, 1200, 0, "0.0002"),
        (1000, 200, 1200, 0, "0.00204"),
    ],
)
def test_cost_categories(input_tokens, cached, written, output_tokens, expected):
    estimate = estimate_model_cost(
        "gpt-6-sol",
        input_tokens=input_tokens,
        cached_input_tokens=cached,
        cache_write_tokens=written,
        output_tokens=output_tokens,
    )
    assert estimate.total_cost_usd == Decimal(expected)
    assert estimate.total_cost_usd == estimate.input_cost_usd + estimate.output_cost_usd


def test_other_providers_keep_existing_estimates():
    for model in DOCUMENT_MODELS:
        if model.provider == "openai":
            continue
        assert estimate_model_cost(
            model.model_id, input_tokens=1000, output_tokens=100, cache_write_tokens=300
        ) == estimate_model_cost(model.model_id, input_tokens=1000, output_tokens=100)


def test_cost_page_includes_cache_writes():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app_pages/cost.py")
    app.session_state["session_usage"] = {
        "synthetic": {
            "gpt-6-sol": {
                "input_tokens": 1000,
                "cached_input_tokens": 200,
                "cache_write_tokens": 300,
                "output_tokens": 100,
            }
        }
    }
    app.run(timeout=30)
    assert not app.exception
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Cache write tokens"] == "300"
    assert metrics["Estimated cost"] == "$0.002790"
    row = app.dataframe[0].value.iloc[0]
    assert row["Model"] == "GPT-6 Sol"
    assert row["Cache write tokens"] == 300


def test_parse_page_defaults_to_sol(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "streamlit_app.py")
    app.session_state["engine_cloud_ai"] = True
    app.run(timeout=60)
    assert not app.exception
    selector = app.selectbox(key="cloud_ai_model")
    assert selector.value == "GPT-6 Sol"
    assert len(selector.options) == 6
    selector.select("Grok 4.6").run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="cloud_ai_model").value == "Grok 4.6"
