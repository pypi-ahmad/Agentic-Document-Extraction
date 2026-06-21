"""Tests for the extraction validation engine and review routing."""

from __future__ import annotations

from app.models.extraction._base import ValidationResult
from app.services.extraction.validation import (
    _validate_required,
    _validate_types,
    clear_rules,
    compute_review_verdict,
    register_rule,
    validate_extraction,
)

# ── Required-field checks ────────────────────────────────────────────


class TestValidateRequired:
    def test_required_present(self):
        results = _validate_required({"name": "Acme"}, [{"name": "name", "required": True}])
        assert len(results) == 1
        assert results[0].valid is True

    def test_required_missing(self):
        results = _validate_required({}, [{"name": "name", "required": True}])
        assert len(results) == 1
        assert results[0].valid is False
        assert "missing" in results[0].message.lower()

    def test_required_empty_string(self):
        results = _validate_required({"name": ""}, [{"name": "name", "required": True}])
        assert results[0].valid is False

    def test_required_none(self):
        results = _validate_required({"name": None}, [{"name": "name", "required": True}])
        assert results[0].valid is False

    def test_optional_missing_ok(self):
        results = _validate_required({}, [{"name": "notes", "required": False}])
        assert results == []

    def test_multiple_fields(self):
        data = {"vendor": "Acme"}
        fields = [
            {"name": "vendor", "required": True},
            {"name": "total", "required": True},
            {"name": "notes", "required": False},
        ]
        results = _validate_required(data, fields)
        valid_names = {r.field_name for r in results if r.valid}
        invalid_names = {r.field_name for r in results if not r.valid}
        assert valid_names == {"vendor"}
        assert invalid_names == {"total"}


# ── Type checks ──────────────────────────────────────────────────────


class TestValidateTypes:
    def test_number_valid_int(self):
        results = _validate_types({"total": 100}, [{"name": "total", "field_type": "number"}])
        assert results == []

    def test_number_valid_float(self):
        results = _validate_types({"total": 99.5}, [{"name": "total", "field_type": "number"}])
        assert results == []

    def test_number_string_castable(self):
        results = _validate_types({"total": "42"}, [{"name": "total", "field_type": "number"}])
        assert results == []

    def test_number_invalid(self):
        results = _validate_types({"total": "abc"}, [{"name": "total", "field_type": "number"}])
        assert len(results) == 1
        assert results[0].valid is False

    def test_boolean_valid(self):
        results = _validate_types({"flag": True}, [{"name": "flag", "field_type": "boolean"}])
        assert results == []

    def test_boolean_invalid(self):
        results = _validate_types({"flag": "yes"}, [{"name": "flag", "field_type": "boolean"}])
        assert len(results) == 1
        assert results[0].valid is False

    def test_date_valid(self):
        results = _validate_types({"date": "2024-01-15"}, [{"name": "date", "field_type": "date"}])
        assert results == []

    def test_date_invalid_format(self):
        results = _validate_types({"date": "01/15/2024"}, [{"name": "date", "field_type": "date"}])
        assert len(results) == 1
        assert results[0].valid is False
        assert "ISO" in results[0].message

    def test_list_valid(self):
        results = _validate_types({"items": [1, 2]}, [{"name": "items", "field_type": "list"}])
        assert results == []

    def test_list_invalid(self):
        results = _validate_types(
            {"items": "not a list"}, [{"name": "items", "field_type": "list"}]
        )
        assert len(results) == 1
        assert results[0].valid is False

    def test_object_valid(self):
        results = _validate_types(
            {"addr": {"line1": "x"}}, [{"name": "addr", "field_type": "object"}]
        )
        assert results == []

    def test_object_invalid(self):
        results = _validate_types(
            {"addr": "123 Main St"}, [{"name": "addr", "field_type": "object"}]
        )
        assert len(results) == 1
        assert results[0].valid is False

    def test_string_any_value_ok(self):
        results = _validate_types({"name": 123}, [{"name": "name", "field_type": "string"}])
        assert results == []

    def test_skips_none_values(self):
        results = _validate_types({"total": None}, [{"name": "total", "field_type": "number"}])
        assert results == []


# ── Business rule hooks ──────────────────────────────────────────────


class TestBusinessRules:
    def setup_method(self):
        clear_rules()

    def teardown_method(self):
        clear_rules()

    def test_register_and_run(self):
        @register_rule
        def check_total(data, fields):
            if data.get("total", 0) < 0:
                return [ValidationResult(field_name="total", valid=False, message="Negative total")]
            return []

        results = validate_extraction(
            {"total": -5}, [{"name": "total", "required": True, "field_type": "number"}]
        )
        messages = [r.message for r in results if not r.valid]
        assert "Negative total" in messages

    def test_rule_not_run_when_not_registered(self):
        results = validate_extraction(
            {"total": -5}, [{"name": "total", "required": True, "field_type": "number"}]
        )
        messages = [r.message for r in results if not r.valid]
        assert "Negative total" not in messages

    def test_multiple_rules(self):
        @register_rule
        def rule_a(data, fields):
            return [ValidationResult(field_name=None, valid=False, message="Rule A")]

        @register_rule
        def rule_b(data, fields):
            return [ValidationResult(field_name=None, valid=False, message="Rule B")]

        results = validate_extraction({}, [])
        messages = [r.message for r in results if not r.valid]
        assert "Rule A" in messages
        assert "Rule B" in messages


# ── Review verdict ───────────────────────────────────────────────────


class TestComputeReviewVerdict:
    def test_all_valid(self):
        results = [
            ValidationResult(field_name="a", valid=True, message=""),
            ValidationResult(field_name="b", valid=True, message=""),
        ]
        assert compute_review_verdict(results) == "valid"

    def test_empty_results(self):
        assert compute_review_verdict([]) == "valid"

    def test_soft_failure_needs_review(self):
        results = [
            ValidationResult(field_name="a", valid=True, message=""),
            ValidationResult(field_name="b", valid=False, message="Missing field 'b'"),
        ]
        assert compute_review_verdict(results) == "needs_review"

    def test_hard_prefix_still_needs_review(self):
        """[HARD] prefix no longer triggers 'invalid' — just needs_review."""
        results = [
            ValidationResult(field_name="a", valid=True, message=""),
            ValidationResult(field_name="b", valid=False, message="[HARD] Checksum mismatch"),
        ]
        assert compute_review_verdict(results) == "needs_review"


# ── Aggregate validate_extraction ────────────────────────────────────


class TestValidateExtraction:
    def setup_method(self):
        clear_rules()

    def teardown_method(self):
        clear_rules()

    def test_full_valid_extraction(self):
        data = {"vendor": "Acme", "total": 100, "date": "2024-01-15"}
        fields = [
            {"name": "vendor", "required": True, "field_type": "string"},
            {"name": "total", "required": True, "field_type": "number"},
            {"name": "date", "required": False, "field_type": "date"},
        ]
        results = validate_extraction(data, fields)
        assert all(r.valid for r in results)

    def test_mixed_errors(self):
        data = {"vendor": "Acme"}
        fields = [
            {"name": "vendor", "required": True, "field_type": "string"},
            {"name": "total", "required": True, "field_type": "number"},
        ]
        results = validate_extraction(data, fields)
        valid = [r for r in results if r.valid]
        invalid = [r for r in results if not r.valid]
        assert len(valid) >= 1
        assert len(invalid) >= 1

    def test_type_error_on_present_field(self):
        data = {"vendor": "Acme", "total": "not-a-number"}
        fields = [
            {"name": "vendor", "required": True, "field_type": "string"},
            {"name": "total", "required": True, "field_type": "number"},
        ]
        results = validate_extraction(data, fields)
        type_errors = [r for r in results if not r.valid and "number" in r.message]
        assert len(type_errors) == 1

    def test_business_rule_returning_empty(self):
        """A rule that returns [] should not affect the verdict."""

        @register_rule
        def no_op_rule(data, fields):
            return []

        data = {"vendor": "Acme"}
        fields = [{"name": "vendor", "required": True, "field_type": "string"}]
        results = validate_extraction(data, fields)
        assert all(r.valid for r in results)

    def test_empty_schema_fields(self):
        """No schema fields → no validation results."""
        results = validate_extraction({"extra_key": "value"}, [])
        assert results == []

    def test_unknown_field_type_passes(self):
        """Unknown field types should be silently accepted."""
        data = {"x": "anything"}
        fields = [{"name": "x", "required": True, "field_type": "custom_type"}]
        results = validate_extraction(data, fields)
        failures = [r for r in results if not r.valid]
        assert failures == []
