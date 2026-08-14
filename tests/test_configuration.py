from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def test_env_example_contains_only_safe_placeholders() -> None:
    values = dotenv_values(ROOT / ".env.example")

    assert values == {
        "OPENAI_API_KEY": "replace-with-your-openai-api-key",
        "OPENAI_BASE_URL": "https://api.openai.com",
        "XAI_API_KEY": "replace-with-your-xai-api-key",
        "GEMINI_API_KEY": "replace-with-your-gemini-api-key",
        "ANTHROPIC_API_KEY": "replace-with-your-anthropic-api-key",
        "AGNES_API_KEY": "replace-with-your-agnes-api-key",
    }
