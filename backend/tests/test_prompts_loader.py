"""Tests for the versioned prompt loader and the prompt module shim."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.llm import prompts as prompts_module
from app.services.llm import prompts_loader as loader_module
from app.services.llm.prompts_loader import (
    Prompt,
    PromptNotFoundError,
    index,
    list_prompts,
    load_prompt,
)

# ── load_prompt ──────────────────────────────────────────────────────


def test_load_extraction_v1() -> None:
    p = load_prompt("extraction", "v1")
    assert p.name == "extraction"
    assert p.version == "v1"
    assert "{text}" in p.body
    assert "{fields_block}" in p.body
    assert "document data extraction assistant" in p.body


def test_load_reflection_v1() -> None:
    p = load_prompt("reflection", "v1")
    assert p.name == "reflection"
    assert "{attempt}" in p.body
    assert "{previous_data}" in p.body
    assert "{errors_block}" in p.body


def test_load_prompt_renders() -> None:
    p = load_prompt("extraction", "v1")
    rendered = p.render(text="Hello", fields_block="- foo")
    assert "Hello" in rendered
    assert "- foo" in rendered
    # Untouched placeholders should be KeyError if accessed.
    with pytest.raises(KeyError):
        p.render()


def test_load_prompt_missing_raises() -> None:
    with pytest.raises(PromptNotFoundError):
        load_prompt("nonexistent", "v1")


# ── list_prompts / index ─────────────────────────────────────────────


def test_list_prompts_includes_v1() -> None:
    pairs = list_prompts()
    assert ("extraction", "v1") in pairs
    assert ("reflection", "v1") in pairs


def test_index_returns_metadata_only() -> None:
    idx = index()
    assert "v1" in idx
    assert "extraction" in idx["v1"]
    assert "reflection" in idx["v1"]
    entry = idx["v1"]["extraction"]
    assert "description" in entry
    assert "model_floor" in entry
    # The body is not included in the index (saves memory).
    assert "body" not in entry


# ── Legacy builders (backward compat) ───────────────────────────────


def test_build_extraction_prompt_legacy() -> None:
    text = prompts_module.build_extraction_prompt(
        "Acme invoice",
        [{"name": "vendor", "field_type": "string", "required": True}],
    )
    assert "Acme invoice" in text
    assert "vendor" in text
    assert "_confidence" in text


def test_build_reflection_prompt_legacy() -> None:
    text = prompts_module.build_reflection_prompt(
        "doc text",
        [{"name": "vendor", "field_type": "string", "required": True}],
        previous_data={"vendor": "Acme"},
        validation_errors=["missing total"],
        attempt=1,
    )
    assert "doc text" in text
    assert "Acme" in text
    assert "missing total" in text
    assert "REFLECTION ATTEMPT" in text
    assert "attempt 1" in text.lower() or "1" in text  # attempt is rendered


def test_build_prompt_returns_prompt() -> None:
    p = prompts_module.build_prompt("extraction")
    assert isinstance(p, Prompt)


# ── Front-matter is strict ──────────────────────────────────────────


def test_load_rejects_file_without_front_matter(tmp_path: Path) -> None:
    p = tmp_path / "v9"
    p.mkdir()
    (p / "broken.md").write_text("no front matter here\njust body\n")
    with pytest.raises(ValueError, match="front-matter"):
        load_prompt("broken", "v9", prompts_dir=tmp_path)


def test_resolve_prompts_dir_honors_env_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custom = tmp_path / "custom-prompts"
    monkeypatch.setenv("ADE_PROMPTS_DIR", str(custom))
    assert loader_module._resolve_prompts_dir() == custom


def test_resolve_prompts_dir_falls_back_to_package_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_prompts = tmp_path / "repo-prompts"
    package_prompts = tmp_path / "package-prompts"
    package_prompts.mkdir()
    monkeypatch.delenv("ADE_PROMPTS_DIR", raising=False)
    monkeypatch.setattr(loader_module, "_REPO_PROMPTS_DIR", repo_prompts)
    monkeypatch.setattr(loader_module, "_PACKAGE_PROMPTS_DIR", package_prompts)
    assert loader_module._resolve_prompts_dir() == package_prompts
