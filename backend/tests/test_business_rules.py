"""Tests for the built-in business rules module."""

from typing import ClassVar

import pytest

from app.services.extraction.business_rules import check_financial_totals
from app.services.extraction.validation import clear_rules


@pytest.fixture(autouse=True)
def _clean_rules():
    """Prevent rules from accumulating across test-module imports."""
    yield
    clear_rules()


class TestCheckFinancialTotals:
    """Exercise the check_financial_totals business rule."""

    _fields_with_totals: ClassVar[list[dict]] = [
        {"name": "subtotal", "field_type": "number", "required": False},
        {"name": "total_amount", "field_type": "number", "required": False},
        {"name": "tax_amount", "field_type": "number", "required": False},
    ]

    def test_valid_totals(self):
        data = {"subtotal": 100, "total_amount": 110, "tax_amount": 10}
        results = check_financial_totals(data, self._fields_with_totals)
        assert all(r.valid for r in results)

    def test_total_less_than_subtotal(self):
        data = {"subtotal": 200, "total_amount": 150, "tax_amount": 0}
        results = check_financial_totals(data, self._fields_with_totals)
        failed = [r for r in results if not r.valid]
        assert len(failed) == 1
        assert failed[0].field_name == "total_amount"
        assert "less than subtotal" in failed[0].message

    def test_negative_tax(self):
        data = {"subtotal": 100, "total_amount": 100, "tax_amount": -5}
        results = check_financial_totals(data, self._fields_with_totals)
        failed = [r for r in results if not r.valid]
        assert len(failed) == 1
        assert failed[0].field_name == "tax_amount"
        assert "negative" in failed[0].message

    def test_equal_total_and_subtotal_ok(self):
        data = {"subtotal": 100, "total_amount": 100}
        results = check_financial_totals(data, self._fields_with_totals)
        assert all(r.valid for r in results) or results == []

    def test_missing_fields_skipped(self):
        """Rule should silently skip when schema lacks the relevant fields."""
        data = {"vendor_name": "Acme", "date": "2024-01-01"}
        fields = [
            {"name": "vendor_name", "field_type": "string", "required": True},
            {"name": "date", "field_type": "date", "required": True},
        ]
        results = check_financial_totals(data, fields)
        assert results == []

    def test_none_values_skipped(self):
        data = {"subtotal": None, "total_amount": None, "tax_amount": None}
        results = check_financial_totals(data, self._fields_with_totals)
        assert results == []

    def test_string_values_skipped(self):
        data = {"subtotal": "abc", "total_amount": "def", "tax_amount": "ghi"}
        results = check_financial_totals(data, self._fields_with_totals)
        assert results == []

    def test_zero_tax_ok(self):
        data = {"tax_amount": 0}
        results = check_financial_totals(data, self._fields_with_totals)
        assert all(r.valid for r in results) or results == []
