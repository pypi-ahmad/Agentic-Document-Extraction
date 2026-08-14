import pytest

from scripts.live_canary import validated_base_url


@pytest.mark.parametrize("url", ["http://127.0.0.1:8010", "http://localhost:8010"])
def test_canary_accepts_loopback_targets(url: str) -> None:
    assert validated_base_url(url, allow_remote=False) == url


def test_canary_rejects_remote_target_without_explicit_consent() -> None:
    with pytest.raises(ValueError, match="--allow-remote"):
        validated_base_url("https://canary.example", allow_remote=False)


def test_canary_rejects_plaintext_remote_target_even_with_consent() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        validated_base_url("http://canary.example", allow_remote=True)


def test_canary_accepts_explicit_https_remote_target() -> None:
    assert (
        validated_base_url("https://canary.example/", allow_remote=True) == "https://canary.example"
    )
