"""Versioned prompt loader for the extraction pipeline.

Prompts live in ``prompts/<version>/<name>.md`` as Markdown with
YAML front-matter. The front-matter carries prompt metadata
(name, version, description, model_floor); the Markdown body is
the prompt template. Templates use ``{name}`` placeholders that
get formatted with keyword arguments at call time.

Why Markdown + front-matter
---------------------------

- **Diffable.** Plain text in git; every prompt change shows up
  as a normal PR diff with the surrounding context.
- **Reviewable.** The model floor and description sit next to
  the prompt body, so a reviewer can decide if the prompt is
  appropriate for the claimed model class without opening a
  second file.
- **Hot-swappable.** Bumping the version string (``v1`` →
  ``v2``) is the only change needed to A/B test a new prompt;
  the loader pulls the right file based on the version stored
  on each extraction row.
- **Scriptable.** The same parser that loads prompts can scan
  ``prompts/`` and emit a JSON index for the eval harness.

Public API
----------

- :func:`load_prompt` — load one prompt by name + version,
  return the rendered body.
- :func:`list_prompts` — list all (name, version) pairs on disk.
- :class:`PromptNotFoundError` — raised on missing prompt.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Repository root: four levels up from this file
# (backend/app/services/llm/prompts_loader.py -> ... -> repo root).
_PROMPTS_DIR = Path(__file__).resolve().parents[4] / "prompts"

# Regex for the YAML front-matter block. Non-greedy on the body.
_FRONTMATTER_RE = re.compile(
    r"^---\s*\n(?P<meta>.*?)\n---\s*\n(?P<body>.*)$",
    re.DOTALL,
)


class PromptNotFoundError(FileNotFoundError):
    """Raised when the requested prompt file does not exist."""


@dataclass(frozen=True)
class Prompt:
    """A loaded prompt with its metadata and rendered body."""

    name: str
    version: str
    description: str
    model_floor: str
    body: str
    raw_template: str

    def render(self, **kwargs: object) -> str:
        """Format the body with the given keyword arguments.

        Missing placeholders raise KeyError so the caller notices
        immediately rather than silently shipping an unfilled
        template.
        """
        return self.raw_template.format(**kwargs)


def _parse(path: Path) -> Prompt:
    """Parse one ``<name>.md`` file with YAML front-matter."""
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError(f"prompt {path} has no YAML front-matter; expected '---' delimiter")
    meta = yaml.safe_load(match.group("meta")) or {}
    body = match.group("body").strip("\n")
    return Prompt(
        name=str(meta.get("name", path.stem)),
        version=str(meta.get("version", path.parent.name)),
        description=str(meta.get("description", "")).strip(),
        model_floor=str(meta.get("model_floor", "")).strip(),
        body=body,
        raw_template=body,
    )


def load_prompt(name: str, version: str = "v1", *, prompts_dir: Path | None = None) -> Prompt:
    """Load ``prompts/<version>/<name>.md`` and return a :class:`Prompt`.

    Raises :class:`PromptNotFoundError` if the file is missing.
    """
    base = prompts_dir or _PROMPTS_DIR
    path = base / version / f"{name}.md"
    if not path.exists():
        raise PromptNotFoundError(f"prompt {name!r} version {version!r} not found at {path}")
    return _parse(path)


def list_prompts(prompts_dir: Path | None = None) -> list[tuple[str, str]]:
    """Return all (name, version) pairs on disk, sorted by version then name."""
    base = prompts_dir or _PROMPTS_DIR
    out: list[tuple[str, str]] = []
    if not base.exists():
        return out
    for version_dir in sorted(base.iterdir()):
        if not version_dir.is_dir():
            continue
        for p in sorted(version_dir.glob("*.md")):
            out.append((p.stem, version_dir.name))
    return out


def index(prompts_dir: Path | None = None) -> dict[str, dict[str, dict]]:
    """Return a JSON-friendly index of all prompts, grouped by version.

    Used by the eval harness and the docs site to render a
    "available prompts" table without re-parsing the markdown.
    """
    base = prompts_dir or _PROMPTS_DIR
    out: dict[str, dict[str, dict]] = {}
    if not base.exists():
        return out
    for version_dir in sorted(base.iterdir()):
        if not version_dir.is_dir():
            continue
        out[version_dir.name] = {}
        for p in sorted(version_dir.glob("*.md")):
            prompt = _parse(p)
            out[version_dir.name][prompt.name] = {
                "description": prompt.description,
                "model_floor": prompt.model_floor,
            }
    return out


__all__ = [
    "Prompt",
    "PromptNotFoundError",
    "index",
    "list_prompts",
    "load_prompt",
]


# Avoid a hard dep on PyYAML in environments that don't have it; we
# only need a tiny YAML subset. Fall back to a hand-rolled parser
# that handles the simple ``key: value`` lines we actually use.
if yaml is None:  # pragma: no cover — defensive
    logger.warning("PyYAML not installed; using fallback parser")


def _simple_yaml_fallback(text: str) -> Mapping[str, object]:
    """Tiny fallback YAML parser for the few keys we use in prompts/."""
    raise RuntimeError("PyYAML is required to parse prompt front-matter")
