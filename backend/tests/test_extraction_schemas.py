"""Tests for extraction result schemas and enum stability."""

from __future__ import annotations

from app.models.enums import FieldType
from app.models.extraction._base import ValidationResult

# ── ValidationResult ─────────────────────────────────────────────────


class TestValidationResult:
    def test_field_level(self):
        vr = ValidationResult(field_name="total_amount", valid=False, message="Must be positive")
        assert not vr.valid
        assert vr.field_name == "total_amount"

    def test_document_level(self):
        vr = ValidationResult(valid=True, message="Checksum OK")
        assert vr.field_name is None
        assert vr.valid


# ── Enum stability ──────────────────────────────────────────────────


class TestExtractionEnums:
    def test_field_type_values(self):
        assert FieldType.STRING == "string"
        assert FieldType.NUMBER == "number"
        assert FieldType.BOOLEAN == "boolean"
        assert FieldType.DATE == "date"
        assert FieldType.LIST == "list"
        assert FieldType.OBJECT == "object"
