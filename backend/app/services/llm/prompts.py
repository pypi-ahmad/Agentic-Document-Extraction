"""Shared prompt builder for structured extraction.

The actual prompt text lives in ``prompts/<version>/<name>.md`` as
versioned Markdown with YAML front-matter. This module is a thin
wrapper that loads the prompt and renders it with the per-call
fields. The legacy ``build_extraction_prompt`` and
``build_reflection_prompt`` functions are kept for backward
compatibility; new code should pass ``prompt_version=...`` and
``schema_version=...`` through :func:`build_prompt` instead.
"""

from __future__ import annotations

import json as _json

from app.services.llm.prompts_loader import (
    Prompt,
    PromptNotFoundError,
    load_prompt,
)


def _fields_block(schema_fields: list[dict]) -> str:
    field_descriptions = []
    for f in schema_fields:
        req = "required" if f.get("required", True) else "optional"
        field_descriptions.append(
            f'  - "{f["name"]}" ({f.get("field_type", "string")}, {req}): {f.get("description", "")}'
        )
    return "\n".join(field_descriptions)


def build_prompt(
    name: str,
    *,
    version: str = "v1",
    **fields: object,
) -> Prompt:
    """Load a versioned prompt by name and return the :class:`Prompt`.

    The caller can then call ``prompt.render(**fields)`` to fill
    the template. Kept separate from the legacy builders so the
    new versioned path is the recommended one.
    """
    return load_prompt(name, version)


def build_extraction_prompt(text: str, schema_fields: list[dict]) -> str:
    """Legacy builder: returns the v1 extraction prompt rendered.

    Equivalent to ``load_prompt('extraction', 'v1').render(...)``;
    kept for backward compatibility with code paths that still
    call it directly.
    """
    return load_prompt("extraction", "v1").render(
        text=text,
        fields_block=_fields_block(schema_fields),
    )


def build_reflection_prompt(
    text: str,
    schema_fields: list[dict],
    *,
    previous_data: dict,
    validation_errors: list[str],
    attempt: int,
) -> str:
    """Legacy builder: returns the v1 reflection prompt rendered.

    Equivalent to ``load_prompt('reflection', 'v1').render(...)``;
    kept for backward compatibility.
    """
    errors_block = "\n".join(f"  - {e}" for e in validation_errors) or "  (none)"
    return load_prompt("reflection", "v1").render(
        text=text,
        fields_block=_fields_block(schema_fields),
        previous_data=_json.dumps(previous_data, indent=2),
        errors_block=errors_block,
        attempt=attempt,
    )


__all__ = [
    "PromptNotFoundError",
    "build_extraction_prompt",
    "build_prompt",
    "build_reflection_prompt",
]
