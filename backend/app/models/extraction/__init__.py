"""Extraction result models.

Public API
----------
* :class:`ValidationResult` — per-field or document-level validation outcome
"""

from app.models.extraction._base import ValidationResult

__all__ = [
    "ValidationResult",
]
