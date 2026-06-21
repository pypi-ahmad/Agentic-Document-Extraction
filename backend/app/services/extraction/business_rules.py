"""Built-in business rules for common document-type validations.

Each rule is registered via :func:`~app.services.extraction.validation.register_rule`
and runs automatically during the ``validate`` pipeline node.

Rules receive the full extracted data dict and the schema field
definitions, returning zero or more
:class:`~app.models.extraction._base.ValidationResult` entries.
"""

from __future__ import annotations

from typing import Any

from app.models.extraction._base import ValidationResult
from app.services.extraction.validation import register_rule


@register_rule
def check_financial_totals(
    data: dict[str, Any],
    fields: list[dict[str, Any]],
) -> list[ValidationResult]:
    """Flag invoices/receipts where totals are inconsistent.

    Checks:
    - If both ``subtotal`` and ``total_amount`` are present,
      ``total_amount`` should be >= ``subtotal``.
    - If ``tax_amount`` is present and negative, flag it.
    """
    results: list[ValidationResult] = []

    field_names = {f["name"] for f in fields}

    subtotal = data.get("subtotal")
    total_amount = data.get("total_amount")
    tax_amount = data.get("tax_amount")

    # Only apply checks when both fields exist in the schema and have values
    if (
        "subtotal" in field_names
        and "total_amount" in field_names
        and isinstance(subtotal, (int, float))
        and isinstance(total_amount, (int, float))
        and total_amount < subtotal
    ):
        results.append(
            ValidationResult(
                field_name="total_amount",
                valid=False,
                message=(
                    f"Total amount ({total_amount}) is less than subtotal ({subtotal}). "
                    f"Please verify the amounts."
                ),
            )
        )

    if "tax_amount" in field_names and isinstance(tax_amount, (int, float)) and tax_amount < 0:
        results.append(
            ValidationResult(
                field_name="tax_amount",
                valid=False,
                message=f"Tax amount ({tax_amount}) is negative. Please verify.",
            )
        )

    return results
