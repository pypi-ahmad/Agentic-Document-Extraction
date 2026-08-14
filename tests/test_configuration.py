import tomllib
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def test_streamlit_uses_red_black_dark_theme() -> None:
    with (ROOT / ".streamlit" / "config.toml").open("rb") as config_file:
        config = tomllib.load(config_file)

    assert config["theme"] == {
        "base": "dark",
        "primaryColor": "#D32F2F",
        "backgroundColor": "#0B0B0D",
        "secondaryBackgroundColor": "#17171A",
        "textColor": "#F2F2F2",
        "borderColor": "#3D2023",
        "showWidgetBorder": True,
        "baseRadius": "6px",
        "buttonRadius": "6px",
        "sidebar": {
            "backgroundColor": "#111113",
            "secondaryBackgroundColor": "#211517",
            "textColor": "#F2F2F2",
            "borderColor": "#462327",
        },
    }


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

    assert 'set "UV_LINK_MODE=copy"' in launcher
    assert 'import torch.backends; from docling.datamodel.base_models import DocumentStream' in launcher
    assert "--reinstall-package torch --reinstall-package torchvision" in launcher
    assert "sync --check --locked --python 3.12.10 --extra %TORCH_EXTRA%" in launcher
    assert "sync --check --locked --python 3.12.10 --extra cpu" in launcher
    assert "if defined MODELS_READY goto :models_ready" in launcher
    assert '"%VENV_PYTHON%" -m streamlit cache clear' in launcher
    assert '"%VENV_PYTHON%" -m streamlit run workspace_app.py --server.port=8551' in launcher
    assert (
        '"%UV_EXE%" run --locked --python 3.12.10 --extra %TORCH_EXTRA% '
        "streamlit run" not in launcher
    )


def test_linux_launcher_skips_completed_setup() -> None:
    launcher = (ROOT / "Paperplane.sh").read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in launcher
    assert 'export UV_LINK_MODE="${UV_LINK_MODE:-copy}"' in launcher
    assert 'import torch.backends; from docling.datamodel.base_models import DocumentStream' in launcher
    assert "--reinstall-package torch --reinstall-package torchvision" in launcher
    assert '"$uv_exe" sync --check --locked --python 3.12.10 --extra "$torch_extra"' in launcher
    assert "sudo apt-get install -y libreoffice" in launcher
    assert "nvidia-smi" in launcher
    assert "models download layout tableformer rapidocr --quiet" in launcher
    assert '"$venv_python" -m streamlit cache clear' in launcher
    assert 'exec "$venv_python" -m streamlit run workspace_app.py --server.port=8551' in launcher
