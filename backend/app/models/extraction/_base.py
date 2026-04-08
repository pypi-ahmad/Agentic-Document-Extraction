"""Validation result model used by the extraction pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Machine-generated validation outcome for a field or the document.

    ``field_name`` is ``None`` for document-level validation errors
    (e.g. checksum mismatch between total and line items).
    """

    field_name: str | None = Field(
        default=None,
        description="Field this result applies to, or null for document-level.",
    )
    valid: bool = Field(
        ...,
        description="Whether the field or document passed this validation check.",
    )
    message: str = Field(
        default="",
        max_length=500,
        description="Human-readable explanation of the validation outcome.",
    )
