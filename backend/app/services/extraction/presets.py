"""Built-in document type presets for common business documents.

Each preset is a ready-to-use schema template with field definitions
tuned for a specific document type.  Users can create schemas from
presets via the API or the frontend "Use template" flow.

Presets are NOT persisted in the database — they're static definitions
served by the ``/api/schemas/presets`` endpoint.  Creating a schema from
a preset copies the fields into a normal user-owned schema row.

Only document types that have been validated end-to-end belong here.
Add new presets only after confirming they produce reliable extraction
results with at least one LLM provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PresetField:
    """A single field in a preset template."""

    name: str
    description: str
    field_type: str = "string"
    required: bool = True


@dataclass(frozen=True)
class SchemaPreset:
    """A built-in document-type schema template."""

    id: str
    name: str
    description: str
    doc_type: str
    fields: list[PresetField] = field(default_factory=list)


# ── Invoice ──────────────────────────────────────────────────────────

INVOICE = SchemaPreset(
    id="preset-invoice",
    name="Invoice",
    description="Standard vendor invoice with line items and payment terms.",
    doc_type="invoice",
    fields=[
        PresetField(
            name="vendor_name",
            description="Name of the vendor / supplier",
        ),
        PresetField(
            name="invoice_number",
            description="Invoice or reference number",
        ),
        PresetField(
            name="invoice_date",
            description="Date the invoice was issued",
            field_type="date",
        ),
        PresetField(
            name="due_date",
            description="Payment due date",
            field_type="date",
            required=False,
        ),
        PresetField(
            name="subtotal",
            description="Subtotal before tax",
            field_type="number",
            required=False,
        ),
        PresetField(
            name="tax_amount",
            description="Tax or VAT amount",
            field_type="number",
            required=False,
        ),
        PresetField(
            name="total_amount",
            description="Total amount due",
            field_type="number",
        ),
        PresetField(
            name="currency",
            description="Currency code (e.g. USD, EUR)",
            required=False,
        ),
        PresetField(
            name="line_items",
            description="List of items/services with description and amount",
            field_type="list",
            required=False,
        ),
        PresetField(
            name="payment_terms",
            description="Payment terms (e.g. Net 30)",
            required=False,
        ),
    ],
)

# ── Receipt ──────────────────────────────────────────────────────────

RECEIPT = SchemaPreset(
    id="preset-receipt",
    name="Receipt",
    description="Purchase receipt from a store or service provider.",
    doc_type="receipt",
    fields=[
        PresetField(
            name="merchant_name",
            description="Name of the store or merchant",
        ),
        PresetField(
            name="transaction_date",
            description="Date of the purchase",
            field_type="date",
        ),
        PresetField(
            name="total_amount",
            description="Total amount paid",
            field_type="number",
        ),
        PresetField(
            name="tax_amount",
            description="Tax amount",
            field_type="number",
            required=False,
        ),
        PresetField(
            name="payment_method",
            description="Payment method (e.g. Cash, Credit Card, Debit)",
            required=False,
        ),
        PresetField(
            name="items",
            description="List of purchased items with price",
            field_type="list",
            required=False,
        ),
        PresetField(
            name="receipt_number",
            description="Receipt or transaction number",
            required=False,
        ),
    ],
)


# ── Registry ─────────────────────────────────────────────────────────

PRESETS: dict[str, SchemaPreset] = {
    p.id: p for p in [INVOICE, RECEIPT]
}


def get_preset(preset_id: str) -> SchemaPreset | None:
    """Look up a preset by ID."""
    return PRESETS.get(preset_id)


def list_presets() -> list[SchemaPreset]:
    """Return all available presets."""
    return list(PRESETS.values())
