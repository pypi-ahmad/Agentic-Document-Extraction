from pathlib import Path

from streamlit.testing.v1 import AppTest

from paperplane.contracts import ModelTokenUsage

COST_PATH = Path(__file__).resolve().parents[1] / "app_pages" / "cost.py"


def test_cost_page_aggregates_session_usage_by_model_and_total() -> None:
    app = AppTest.from_file(COST_PATH).run()
    app.session_state["session_usage"] = {
        "parse-1": {
            "gpt-5.6-luna": ModelTokenUsage(
                input_tokens=1_000_000,
                cached_input_tokens=250_000,
                output_tokens=1_000_000,
            ),
            "local-ocr:latest": ModelTokenUsage(input_tokens=20, output_tokens=10),
        },
        "parse-2": {
            "gemini-3.7-flash": ModelTokenUsage(
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            ),
            "agnes-2.5-flash": ModelTokenUsage(input_tokens=100, output_tokens=50),
        },
    }
    app.run()

    metrics = {item.label: item.value for item in app.metric}
    assert metrics == {
        "Input tokens": "2,000,120",
        "Cache tokens": "250,000",
        "Output tokens": "2,000,060",
        "Estimated cost": "$5.8550",
    }
    rows = app.dataframe[0].value.to_dict("records")
    assert {row["Model"] for row in rows} == {
        "Agnes 2.5 Flash",
        "Gemini 3.7 Flash",
        "GPT-5.6 Luna",
        "local-ocr:latest",
        "Total",
    }
    assert (
        next(row for row in rows if row["Model"] == "local-ocr:latest")["Estimated cost"]
        == "$0.000000"
    )
    assert next(row for row in rows if row["Model"] == "Total")["Estimated cost"] == "$5.8550"


def test_cost_page_starts_at_zero() -> None:
    app = AppTest.from_file(COST_PATH).run()

    assert {item.label: item.value for item in app.metric} == {
        "Input tokens": "0",
        "Cache tokens": "0",
        "Output tokens": "0",
        "Estimated cost": "$0.000000",
    }
    assert not app.dataframe
    assert any("No successful model usage" in item.value for item in app.info)
