"""Tests for the security helpers (MIME sniff, SSRF guard, security headers)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.utils.mime import mime_matches_extension, sniff_mime
from app.utils.network import UnsafeOllamaURLError, _is_loopback_host, validate_ollama_base_url

# ── MIME sniff ────────────────────────────────────────────────────────


def test_sniff_mime_pdf(tmp_path: Path) -> None:
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    assert sniff_mime(f) == "pdf"


def test_sniff_mime_png(tmp_path: Path) -> None:
    f = tmp_path / "img.png"
    f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    assert sniff_mime(f) == "png"


def test_sniff_mime_jpeg(tmp_path: Path) -> None:
    f = tmp_path / "img.jpg"
    f.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8)
    assert sniff_mime(f) == "jpeg"


def test_sniff_mime_tiff_little_endian(tmp_path: Path) -> None:
    f = tmp_path / "img.tif"
    f.write_bytes(b"II\x2a\x00" + b"\x00" * 8)
    assert sniff_mime(f) == "tiff"


def test_sniff_mime_tiff_big_endian(tmp_path: Path) -> None:
    f = tmp_path / "img.tif"
    f.write_bytes(b"MM\x00\x2a" + b"\x00" * 8)
    assert sniff_mime(f) == "tiff"


def test_sniff_mime_rejects_script(tmp_path: Path) -> None:
    f = tmp_path / "evil.exe"
    f.write_bytes(b"MZ\x90\x00\x03\x00\x00\x00")
    with pytest.raises(Exception) as exc:
        sniff_mime(f)
    assert "magic" in str(exc.value).lower()


def test_sniff_mime_rejects_empty(tmp_path: Path) -> None:
    f = tmp_path / "empty.bin"
    f.write_bytes(b"")
    with pytest.raises(Exception):
        sniff_mime(f)


def test_mime_matches_extension_true() -> None:
    assert mime_matches_extension("pdf", "pdf")
    assert mime_matches_extension("png", "PNG")
    assert mime_matches_extension("jpeg", "jpg")
    assert mime_matches_extension("jpeg", "jpeg")
    assert mime_matches_extension("tiff", "tif")
    assert mime_matches_extension("tiff", "tiff")


def test_mime_matches_extension_false() -> None:
    assert not mime_matches_extension("pdf", "png")
    assert not mime_matches_extension("jpeg", "pdf")
    assert not mime_matches_extension("tiff", "exe")


# ── SSRF guard ────────────────────────────────────────────────────────


def test_loopback_hosts() -> None:
    assert _is_loopback_host("localhost")
    assert _is_loopback_host("127.0.0.1")
    assert _is_loopback_host("::1")
    assert _is_loopback_host("0.0.0.0")
    assert not _is_loopback_host("8.8.8.8")
    assert not _is_loopback_host("example.com")
    assert not _is_loopback_host("")


def test_validate_ollama_url_localhost_ok() -> None:
    validate_ollama_base_url("http://localhost:11434")
    validate_ollama_base_url("http://127.0.0.1:11434")


def test_validate_ollama_url_remote_rejected() -> None:
    with pytest.raises(UnsafeOllamaURLError):
        validate_ollama_base_url("http://attacker.example.com:11434")


def test_validate_ollama_url_remote_allowed_with_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_ALLOW_PRIVATE_HOSTS", "true")
    validate_ollama_base_url("http://attacker.example.com:11434")


def test_validate_ollama_url_bad_scheme() -> None:
    with pytest.raises(UnsafeOllamaURLError):
        validate_ollama_base_url("ftp://localhost:11434")


def test_validate_ollama_url_no_host() -> None:
    with pytest.raises(UnsafeOllamaURLError):
        validate_ollama_base_url("http://")
