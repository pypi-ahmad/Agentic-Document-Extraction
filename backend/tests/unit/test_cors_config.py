import pytest
from pydantic import ValidationError

from app.config import Settings
from app.constants import SECURITY_HEADERS


def _settings(**overrides) -> Settings:
    values = {
        "openai_api_key": "",
        "anthropic_api_key": "",
        "gemini_api_key": "",
        "xai_api_key": "",
        **overrides,
    }
    return Settings(_env_file=None, **values)


def test_default_origins_pass_validation() -> None:
    settings = _settings()

    assert settings.cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_wildcard_with_default_credentials_rejected_at_startup() -> None:
    with pytest.raises(ValidationError, match="cannot include '\\*'"):
        _settings(cors_origins="*")


def test_wildcard_with_api_key_rejected_even_if_credentials_disabled() -> None:
    with pytest.raises(ValidationError, match="cannot include '\\*'"):
        _settings(cors_origins="*", cors_allow_credentials=False, api_key="secret")


def test_wildcard_allowed_only_when_fully_open_and_unauthenticated() -> None:
    settings = _settings(cors_origins="*", cors_allow_credentials=False, api_key="")

    assert settings.cors_origin_list == ["*"]


def test_wildcard_mixed_with_explicit_origins_still_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot include '\\*'"):
        _settings(cors_origins="https://app.example.com,*")


def test_origin_list_strips_whitespace_and_drops_empty_entries() -> None:
    settings = _settings(cors_origins=" https://a.example.com , , https://b.example.com ")

    assert settings.cors_origin_list == ["https://a.example.com", "https://b.example.com"]


def test_explicit_multi_origin_production_config_passes() -> None:
    settings = _settings(
        cors_origins="https://app.example.com,https://admin.example.com",
        cors_allow_credentials=True,
        api_key="prod-secret",
    )

    assert settings.cors_origin_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_x_frame_options_is_sameorigin_not_deny() -> None:
    """Regression guard: DocumentCanvas/ArtifactPreview iframe document
    previews from this API — DENY would silently break them again."""
    assert SECURITY_HEADERS["X-Frame-Options"] == "SAMEORIGIN"


@pytest.mark.asyncio
async def test_preflight_echoes_allowed_origin_only(client) -> None:
    allowed = await client.options(
        "/api/extraction-schemas",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    disallowed = await client.options(
        "/api/extraction-schemas",
        headers={
            "Origin": "https://not-allowed.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in disallowed.headers
