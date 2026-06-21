"""Field-level validation engine for extraction results.

Provides schema-driven validation (required fields, type checks) and
a pluggable business-rule hook system.  Each validator returns a list of
:class:`~app.models.extraction.ValidationResult` objects that downstream
code (the LangGraph ``validate`` node) aggregates into a review
verdict: ``valid`` or ``needs_review``.

Business-rule hooks
-------------------
Register custom rules with :func:`register_rule`.  A rule receives the
full extracted dict, the schema field definitions, and returns zero or
more ``ValidationResult`` entries.

::

    from app.services.extraction.validation import register_rule


    @register_rule
    def check_total_matches_line_items(data, fields):
        ...
        return [
            ValidationResult(
                field_name="total_amount", valid=False, message="Total does not match line items"
            )
        ]
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.models.extraction._base import ValidationResult

# ── Types ────────────────────────────────────────────────────────────

RuleFunc = Callable[[dict[str, Any], list[dict[str, Any]]], list[ValidationResult]]

# Registry of custom business-rule hooks
_business_rules: list[RuleFunc] = []

# Read confidence threshold from config (allows env-var / .env override).
_LOW_CONFIDENCE_THRESHOLD = settings.confidence_threshold


def register_rule(func: RuleFunc) -> RuleFunc:
    """Decorator to register a business-rule validation hook."""
    _business_rules.append(func)
    return func


def clear_rules() -> None:
    """Remove all registered business rules (for testing)."""
    _business_rules.clear()


# ── Schema-driven validation ─────────────────────────────────────────


def _validate_required(
    data: dict[str, Any],
    fields: list[dict[str, Any]],
) -> list[ValidationResult]:
    """Check that all required fields are present and non-null."""
    results: list[ValidationResult] = []
    for field_def in fields:
        name = field_def["name"]
        required = field_def.get("required", True)
        value = data.get(name)
        if required and (value is None or value == ""):
            results.append(
                ValidationResult(
                    field_name=name,
                    valid=False,
                    message=f"Required field '{name}' is missing or empty.",
                )
            )
        elif required:
            results.append(ValidationResult(field_name=name, valid=True, message=""))
    return results


_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_types(
    data: dict[str, Any],
    fields: list[dict[str, Any]],
) -> list[ValidationResult]:
    """Best-effort type validation for extracted values.

    Does not reject unexpected types — LLM output is inherently flexible.
    Instead, flags mismatches so they can participate in review routing.
    """
    results: list[ValidationResult] = []
    for field_def in fields:
        name = field_def["name"]
        expected_type = field_def.get("field_type", "string")
        value = data.get(name)
        if value is None:
            continue  # handled by required check

        ok = True
        msg = ""

        if expected_type == "number":
            if not isinstance(value, (int, float)):
                try:
                    float(value)
                except (ValueError, TypeError):
                    ok = False
                    msg = f"Field '{name}' expected a number, got '{type(value).__name__}'."
        elif expected_type == "boolean":
            if not isinstance(value, bool):
                ok = False
                msg = f"Field '{name}' expected a boolean, got '{type(value).__name__}'."
        elif expected_type == "date":
            if isinstance(value, str) and not _ISO_DATE_RE.match(value):
                ok = False
                msg = f"Field '{name}' expected ISO date (YYYY-MM-DD), got '{value}'."
        elif expected_type == "list":
            if not isinstance(value, list):
                ok = False
                msg = f"Field '{name}' expected a list, got '{type(value).__name__}'."
        elif expected_type == "object" and not isinstance(value, dict):
            ok = False
            msg = f"Field '{name}' expected an object, got '{type(value).__name__}'."

        if not ok:
            results.append(ValidationResult(field_name=name, valid=False, message=msg))
    return results


# ── Aggregate ────────────────────────────────────────────────────────


def _validate_confidence(
    data: dict[str, Any],
    fields: list[dict[str, Any]],
    confidence: dict[str, float],
) -> list[ValidationResult]:
    """Flag fields where the LLM reported low confidence."""
    results: list[ValidationResult] = []
    for field_def in fields:
        name = field_def["name"]
        value = data.get(name)
        if value is None:
            continue  # already flagged by required check
        score = confidence.get(name)
        if score is not None and score < _LOW_CONFIDENCE_THRESHOLD:
            results.append(
                ValidationResult(
                    field_name=name,
                    valid=False,
                    message=(
                        f"Low confidence ({score:.0%}) on field '{name}'. "
                        f"Please verify the extracted value."
                    ),
                )
            )
    return results


def validate_extraction(
    data: dict[str, Any],
    schema_fields: list[dict[str, Any]],
    confidence: dict[str, float] | None = None,
) -> list[ValidationResult]:
    """Run all validators and return a flat list of results.

    Order: required-check → type-check → confidence-check → business rules.

    Parameters
    ----------
    confidence:
        Optional per-field confidence scores from the LLM.  Fields
        scoring below ``_LOW_CONFIDENCE_THRESHOLD`` are flagged for
        review even if structurally valid.
    """
    results: list[ValidationResult] = []
    results.extend(_validate_required(data, schema_fields))
    results.extend(_validate_types(data, schema_fields))
    if confidence:
        results.extend(_validate_confidence(data, schema_fields, confidence))
    for rule in _business_rules:
        results.extend(rule(data, schema_fields))
    return results


# ── Review routing ───────────────────────────────────────────────────


def compute_review_verdict(validations: list[ValidationResult]) -> str:
    """Determine the overall validation verdict.

    Returns
    -------
    ``"valid"``
        All checks passed.
    ``"needs_review"``
        At least one check failed.
    """
    for v in validations:
        if not v.valid:
            return "needs_review"
    return "valid"
