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

from app.models.schemas import SchemaFieldDef


@dataclass(frozen=True)
class SchemaPreset:
    """A built-in document-type schema template."""

    id: str
    name: str
    description: str
    doc_type: str
    fields: list[SchemaFieldDef] = field(default_factory=list)


# ── Invoice ──────────────────────────────────────────────────────────

INVOICE = SchemaPreset(
    id="preset-invoice",
    name="Invoice",
    description="Standard vendor invoice with line items and payment terms.",
    doc_type="invoice",
    fields=[
        SchemaFieldDef(
            name="vendor_name",
            description="Name of the vendor / supplier",
        ),
        SchemaFieldDef(
            name="invoice_number",
            description="Invoice or reference number",
        ),
        SchemaFieldDef(
            name="invoice_date",
            description="Date the invoice was issued",
            field_type="date",
        ),
        SchemaFieldDef(
            name="due_date",
            description="Payment due date",
            field_type="date",
            required=False,
        ),
        SchemaFieldDef(
            name="subtotal",
            description="Subtotal before tax",
            field_type="number",
            required=False,
        ),
        SchemaFieldDef(
            name="tax_amount",
            description="Tax or VAT amount",
            field_type="number",
            required=False,
        ),
        SchemaFieldDef(
            name="total_amount",
            description="Total amount due",
            field_type="number",
        ),
        SchemaFieldDef(
            name="currency",
            description="Currency code (e.g. USD, EUR)",
            required=False,
        ),
        SchemaFieldDef(
            name="line_items",
            description="List of items/services with description and amount",
            field_type="list",
            required=False,
        ),
        SchemaFieldDef(
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
        SchemaFieldDef(
            name="merchant_name",
            description="Name of the store or merchant",
        ),
        SchemaFieldDef(
            name="transaction_date",
            description="Date of the purchase",
            field_type="date",
        ),
        SchemaFieldDef(
            name="total_amount",
            description="Total amount paid",
            field_type="number",
        ),
        SchemaFieldDef(
            name="tax_amount",
            description="Tax amount",
            field_type="number",
            required=False,
        ),
        SchemaFieldDef(
            name="payment_method",
            description="Payment method (e.g. Cash, Credit Card, Debit)",
            required=False,
        ),
        SchemaFieldDef(
            name="items",
            description="List of purchased items with price",
            field_type="list",
            required=False,
        ),
        SchemaFieldDef(
            name="receipt_number",
            description="Receipt or transaction number",
            required=False,
        ),
    ],
)


# ── Purchase Order ───────────────────────────────────────────────────

PURCHASE_ORDER = SchemaPreset(
    id="preset-purchase-order",
    name="Purchase Order",
    description="Standard purchase order with line items and shipping details.",
    doc_type="purchase_order",
    fields=[
        SchemaFieldDef(
            name="po_number",
            description="Purchase order number",
        ),
        SchemaFieldDef(
            name="order_date",
            description="Date the order was placed",
            field_type="date",
        ),
        SchemaFieldDef(
            name="buyer_name",
            description="Name of the buying company or person",
        ),
        SchemaFieldDef(
            name="supplier_name",
            description="Name of the supplier or vendor",
        ),
        SchemaFieldDef(
            name="delivery_date",
            description="Expected delivery date",
            field_type="date",
            required=False,
        ),
        SchemaFieldDef(
            name="shipping_address",
            description="Delivery / shipping address",
            required=False,
        ),
        SchemaFieldDef(
            name="line_items",
            description="List of ordered items with quantity, description, and unit price",
            field_type="list",
            required=False,
        ),
        SchemaFieldDef(
            name="total_amount",
            description="Total order amount",
            field_type="number",
        ),
        SchemaFieldDef(
            name="currency",
            description="Currency code (e.g. USD, EUR)",
            required=False,
        ),
        SchemaFieldDef(
            name="payment_terms",
            description="Payment terms (e.g. Net 30, COD)",
            required=False,
        ),
    ],
)

# ── Bank Statement ───────────────────────────────────────────────────

BANK_STATEMENT = SchemaPreset(
    id="preset-bank-statement",
    name="Bank Statement",
    description="Monthly bank account statement with transactions summary.",
    doc_type="bank_statement",
    fields=[
        SchemaFieldDef(
            name="bank_name",
            description="Name of the bank or financial institution",
        ),
        SchemaFieldDef(
            name="account_holder",
            description="Name of the account holder",
        ),
        SchemaFieldDef(
            name="account_number",
            description="Account number (may be partially masked)",
            required=False,
        ),
        SchemaFieldDef(
            name="statement_period",
            description="Statement period (e.g. 'Jan 1 - Jan 31, 2025')",
        ),
        SchemaFieldDef(
            name="opening_balance",
            description="Opening/beginning balance",
            field_type="number",
        ),
        SchemaFieldDef(
            name="closing_balance",
            description="Closing/ending balance",
            field_type="number",
        ),
        SchemaFieldDef(
            name="total_deposits",
            description="Total deposits / credits during the period",
            field_type="number",
            required=False,
        ),
        SchemaFieldDef(
            name="total_withdrawals",
            description="Total withdrawals / debits during the period",
            field_type="number",
            required=False,
        ),
        SchemaFieldDef(
            name="currency",
            description="Currency code (e.g. USD, EUR)",
            required=False,
        ),
    ],
)


# ── Registry ─────────────────────────────────────────────────────────

PRESETS: dict[str, SchemaPreset] = {
    p.id: p for p in [INVOICE, RECEIPT, PURCHASE_ORDER, BANK_STATEMENT]
}


def get_preset(preset_id: str) -> SchemaPreset | None:
    """Look up a preset by ID."""
    return PRESETS.get(preset_id)


def list_presets() -> list[SchemaPreset]:
    """Return all available presets."""
    return list(PRESETS.values())
