from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_parser_limits_match_product_contract() -> None:
    settings = Settings(_env_file=None)

    assert settings.max_upload_size_mb == 200
    assert settings.max_document_pages == 500
    assert settings.job_max_concurrent == 1
    assert settings.job_queue_max_depth == 50
    assert settings.job_timeout_seconds == 21600.0
    assert settings.max_page_repairs == 2
    assert settings.max_upload_bytes == 200 * 1024 * 1024
    assert settings.api_key == ""
    assert settings.host == "127.0.0.1"


def test_ollama_endpoint_is_env_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11435")
    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://127.0.0.1:11435"


def test_openai_process_environment_overrides_dotenv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=dotenv-key\nOPENAI_BASE_URL=https://dotenv.example/v1\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "user-environment-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://user-environment.example/v1")

    settings = Settings(_env_file=env_file)

    assert settings.openai_api_key == "user-environment-key"
    assert settings.openai_base_url == "https://user-environment.example/v1"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_page_repairs", -1),
        ("max_page_repairs", 3),
        ("job_queue_max_depth", 0),
        ("job_timeout_seconds", 0),
    ],
)
def test_agentic_settings_reject_out_of_range_values(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: value})
