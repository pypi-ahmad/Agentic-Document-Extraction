"""Load model instructions from version-controlled Markdown files."""

from functools import cache
from pathlib import Path
from string import Template

PROMPT_ROOT = Path(__file__).with_name("prompts")


@cache
def _prompt_source(name: str) -> str:
    if not name or Path(name).name != name:
        raise ValueError("prompt name must be a Markdown filename")
    path = PROMPT_ROOT / name
    if path.suffix.lower() != ".md":
        raise ValueError("prompt files must use the .md extension")
    return path.read_text(encoding="utf-8").strip()


def load_prompt(name: str, /, **values: object) -> str:
    """Load one Markdown prompt and substitute declared template values."""
    return Template(_prompt_source(name)).substitute(
        {key: str(value) for key, value in values.items()}
    )
