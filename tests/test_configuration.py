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
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    }


def test_windows_launcher_skips_completed_setup() -> None:
    launcher = (ROOT / "Paperplane.cmd").read_text(encoding="utf-8")

    assert "sync --check --locked --python 3.12.10 --extra %TORCH_EXTRA%" in launcher
    assert "sync --check --locked --python 3.12.10 --extra cpu" in launcher
    assert "if defined MODELS_READY goto :models_ready" in launcher
    assert '"%VENV_PYTHON%" -m streamlit run workspace_app.py --server.port=8551' in launcher
    assert (
        '"%UV_EXE%" run --locked --python 3.12.10 --extra %TORCH_EXTRA% '
        "streamlit run" not in launcher
    )
