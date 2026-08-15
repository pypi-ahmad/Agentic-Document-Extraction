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
        "GOOGLE_API_KEY": "replace-with-your-google-api-key",
        "ANTHROPIC_API_KEY": "replace-with-your-anthropic-api-key",
        "AGNES_API_KEY": "replace-with-your-agnes-api-key",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
    }


def test_windows_launcher_skips_completed_setup() -> None:
    launcher = (ROOT / "Paperplane.cmd").read_text(encoding="utf-8")

    assert 'set "UV_LINK_MODE=copy"' in launcher
    assert launcher.count("--link-mode copy") == 3
    assert 'set "PAPERPLANE_ROOT=%CD%"' in launcher
    assert "\\Paperplane.cmd*" in launcher
    assert "taskkill.exe /PID" in launcher
    assert "Stopped the previous Paperplane run." in launcher
    assert "Port 8551 is used by another application." in launcher
    assert "*streamlit run workspace_app.py*" in launcher
    assert "validate_torch_runtime(); from docling.datamodel.base_models" in launcher
    assert "--reinstall-package torch --reinstall-package torchvision" in launcher
    assert "validate_torch_runtime" in launcher
    assert "--inexact" in launcher
    assert "sync --check --locked --python 3.12.10 --extra %TORCH_EXTRA%" in launcher
    assert "sync --check --locked --python 3.12.10 --extra cpu" in launcher
    assert '"%VENV_PYTHON%" -m paperplane.model_store --prepare' in launcher
    assert 'reg.exe query "HKCU\\Environment" /v GOOGLE_API_KEY' in launcher
    assert "Google API credential is available to Paperplane." in launcher
    assert "models download layout tableformer rapidocr" not in launcher
    assert '"%VENV_PYTHON%" -m streamlit cache clear' in launcher
    assert "*paperplane.streamlit_runner run workspace_app.py*" in launcher
    assert (
        '"%VENV_PYTHON%" -m paperplane.streamlit_runner run workspace_app.py '
        "--server.port=8551" in launcher
    )
    assert (
        '"%UV_EXE%" run --locked --python 3.12.10 --extra %TORCH_EXTRA% '
        "streamlit run" not in launcher
    )


def test_linux_launcher_skips_completed_setup() -> None:
    launcher = (ROOT / "Paperplane.sh").read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in launcher
    assert 'export UV_LINK_MODE="${UV_LINK_MODE:-copy}"' in launcher
    assert launcher.count("--link-mode copy") == 3
    assert "validate_torch_runtime(); from docling.datamodel.base_models" in launcher
    assert "--reinstall-package torch --reinstall-package torchvision" in launcher
    assert "validate_torch_runtime" in launcher
    assert "--inexact" in launcher
    assert '"$uv_exe" sync --check --locked --python 3.12.10 --extra "$torch_extra"' in launcher
    assert "sudo apt-get install -y libreoffice" in launcher
    assert "nvidia-smi" in launcher
    assert '"$venv_python" -m paperplane.model_store --prepare' in launcher
    assert "models download layout tableformer rapidocr" not in launcher
    assert '&& -z "${GOOGLE_API_KEY:-}"' in launcher
    assert '"$venv_python" -m streamlit cache clear' in launcher
    assert (
        'exec "$venv_python" -m paperplane.streamlit_runner run workspace_app.py '
        "--server.port=8551" in launcher
    )


def test_workspace_exposes_shared_stop_and_clear_control() -> None:
    workspace = (ROOT / "workspace_app.py").read_text(encoding="utf-8")

    assert '"Stop and clear"' in workspace
    assert "@st.dialog" in workspace
    assert "st.cache_data.clear()" in workspace
    assert "st.cache_resource.clear()" in workspace
    assert "st.session_state.clear()" in workspace
    assert workspace.index("with st.sidebar:") < workspace.index("navigation.run()")


def test_workspace_replaces_benchmarks_with_session_cost() -> None:
    workspace = (ROOT / "workspace_app.py").read_text(encoding="utf-8")

    assert 'st.Page("app_pages/cost.py", title="Cost"' in workspace
    assert "app_pages/benchmarks.py" not in workspace
