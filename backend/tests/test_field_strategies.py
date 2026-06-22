"""Tests for the v0.5.0 schema-aware field strategies."""

from __future__ import annotations

import pytest

from app.services.extraction.field_strategies import (
    AddressStrategy,
    BooleanStrategy,
    CurrencyStrategy,
    DateStrategy,
    FieldValidationError,
    IDStrategy,
    ListStrategy,
    NumberStrategy,
    ObjectStrategy,
    SignatureStrategy,
    StringStrategy,
    TableStrategy,
    available_kinds,
    get_strategy,
    normalize_with_strategy,
    render_fields_block,
)

# ── String strategy ───────────────────────────────────────────────


def test_string_normalize_trims() -> None:
    s = StringStrategy()
    assert s.normalize("  hello  ") == "hello"


def test_string_normalize_none() -> None:
    s = StringStrategy()
    assert s.normalize(None) is None


def test_string_validate_basic() -> None:
    s = StringStrategy()
    assert s.validate("hi") == []
    assert s.validate(None) == ["required"]
    assert s.validate(123) == ["expected string, got int"]


# ── Number strategy ──────────────────────────────────────────────


def test_number_normalize_int() -> None:
    s = NumberStrategy()
    assert s.normalize("123") == 123
    assert s.normalize(123) == 123


def test_number_normalize_float() -> None:
    s = NumberStrategy()
    assert s.normalize("12.34") == 12.34
    assert s.normalize(12.34) == 12.34


def test_number_normalize_strips_currency() -> None:
    s = NumberStrategy()
    assert s.normalize("$1,234.50") == 1234.50
    assert s.normalize("1,234,567") == 1234567


def test_number_normalize_rejects_bool() -> None:
    s = NumberStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize(True)


def test_number_normalize_invalid() -> None:
    s = NumberStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("not a number")


def test_number_validate() -> None:
    s = NumberStrategy()
    assert s.validate(123) == []
    assert s.validate(None) == ["required"]
    assert s.validate("not a number") == ["expected number, got str"]


def test_number_regex_hints() -> None:
    s = NumberStrategy()
    assert len(s.regex_hints) >= 1
    # Sanity check: at least one of the patterns matches a number
    assert any(p.search("123") for p in s.regex_hints)


# ── Boolean strategy ─────────────────────────────────────────────


def test_boolean_normalize_truthy_strings() -> None:
    s = BooleanStrategy()
    for token in ("true", "yes", "y", "1", "t", "TRUE", "Yes"):
        assert s.normalize(token) is True


def test_boolean_normalize_falsy_strings() -> None:
    s = BooleanStrategy()
    for token in ("false", "no", "n", "0", "f", "FALSE", "No"):
        assert s.normalize(token) is False


def test_boolean_normalize_invalid() -> None:
    s = BooleanStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("maybe")


def test_boolean_validate() -> None:
    s = BooleanStrategy()
    assert s.validate(True) == []
    assert s.validate(None) == ["required"]
    assert s.validate(1) == ["expected bool, got int"]


# ── Date strategy ────────────────────────────────────────────────


def test_date_normalize_iso() -> None:
    s = DateStrategy()
    assert s.normalize("2026-01-15") == "2026-01-15"


def test_date_normalize_slash_formats() -> None:
    s = DateStrategy()
    assert s.normalize("01/15/2026") == "2026-01-15"
    assert s.normalize("2026/01/15") == "2026-01-15"


def test_date_normalize_long_form() -> None:
    s = DateStrategy()
    assert s.normalize("January 15, 2026") == "2026-01-15"


def test_date_normalize_invalid() -> None:
    s = DateStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("not a date")


def test_date_validate() -> None:
    s = DateStrategy()
    assert s.validate("2026-01-15") == []
    assert s.validate(None) == ["required"]
    assert s.validate("01/15/2026") != []  # not ISO


# ── Currency strategy ────────────────────────────────────────────


def test_currency_normalize_dict() -> None:
    s = CurrencyStrategy()
    assert s.normalize({"amount": 100.0, "currency": "USD"}) == {
        "amount": 100.0,
        "currency": "USD",
    }


def test_currency_normalize_dict_default_currency() -> None:
    s = CurrencyStrategy()
    assert s.normalize({"amount": 100.0}) == {"amount": 100.0, "currency": "USD"}


def test_currency_normalize_dict_invalid_currency() -> None:
    s = CurrencyStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize({"amount": 100, "currency": "USDD"})


def test_currency_normalize_string_with_currency() -> None:
    s = CurrencyStrategy()
    assert s.normalize("USD 1,234.50") == {"amount": 1234.50, "currency": "USD"}
    assert s.normalize("1,234.50 EUR") == {"amount": 1234.50, "currency": "EUR"}


def test_currency_normalize_string_no_currency() -> None:
    s = CurrencyStrategy()
    assert s.normalize("1,234.50") == {"amount": 1234.50, "currency": "USD"}


def test_currency_normalize_number() -> None:
    s = CurrencyStrategy()
    assert s.normalize(1234.5) == {"amount": 1234.5, "currency": "USD"}


def test_currency_normalize_invalid() -> None:
    s = CurrencyStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("not currency")


def test_currency_validate() -> None:
    s = CurrencyStrategy()
    assert s.validate({"amount": 100, "currency": "USD"}) == []
    assert s.validate(None) == ["required"]
    assert s.validate("100") != []
    assert s.validate({"amount": "x", "currency": "USD"}) == ["'amount' must be numeric"]
    assert s.validate({"amount": 100, "currency": "USDD"}) == ["invalid currency code: 'USDD'"]


# ── ID strategy ──────────────────────────────────────────────────


def test_id_normalize_uppercases_and_trims() -> None:
    s = IDStrategy()
    assert s.normalize("abc-123") == "ABC-123"


def test_id_too_short() -> None:
    s = IDStrategy(min_length=5)
    with pytest.raises(FieldValidationError):
        s.normalize("abc")


def test_id_too_long() -> None:
    s = IDStrategy(max_length=5)
    with pytest.raises(FieldValidationError):
        s.normalize("abcdefghij")


def test_id_with_pattern() -> None:
    import re

    s = IDStrategy(pattern=re.compile(r"^[A-Z]{2}-\d{4}$"))
    assert s.normalize("AB-1234") == "AB-1234"
    with pytest.raises(FieldValidationError):
        s.normalize("AB1234")


def test_id_validate() -> None:
    import re

    s = IDStrategy(min_length=3, pattern=re.compile(r"^\d+$"))
    assert s.validate("123") == []
    assert s.validate(None) == ["required"]
    assert s.validate("12") == ["id too short: 2 < 3"]
    assert s.validate("abc") == ["id does not match expected pattern"]


# ── Address strategy ────────────────────────────────────────────


def test_address_normalize_string() -> None:
    s = AddressStrategy()
    out = s.normalize("123 Main St,   Springfield,   IL 62701")
    assert out == {"raw": "123 Main St, Springfield, IL 62701"}


def test_address_normalize_dict() -> None:
    s = AddressStrategy()
    out = s.normalize({"street": "  123 Main  ", "city": "Springfield"})
    assert out == {"street": "123 Main", "city": "Springfield"}


def test_address_normalize_invalid() -> None:
    s = AddressStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize(123)


def test_address_validate_short_string() -> None:
    s = AddressStrategy()
    assert s.validate("hi") == ["address looks too short"]


def test_address_validate_empty_dict() -> None:
    s = AddressStrategy()
    assert s.validate({}) == ["address dict is empty"]


# ── Table strategy ──────────────────────────────────────────────


def test_table_normalize_list_of_lists() -> None:
    s = TableStrategy()
    out = s.normalize([["A", "B"], ["1", "2"]])
    assert out == [["A", "B"], ["1", "2"]]


def test_table_normalize_list_of_dicts() -> None:
    s = TableStrategy()
    out = s.normalize([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
    assert out == [["1", "2"], ["3", "4"]]


def test_table_normalize_invalid() -> None:
    s = TableStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("not a list")
    with pytest.raises(FieldValidationError):
        s.normalize([1, 2, 3])  # not a list of rows


def test_table_validate_inconsistent_widths() -> None:
    s = TableStrategy()
    assert s.validate([["A", "B"], ["1"]]) == ["rows have inconsistent widths: [1, 2]"]


def test_table_validate_empty() -> None:
    s = TableStrategy()
    assert s.validate([]) == ["table is empty"]


# ── Signature strategy ──────────────────────────────────────────


def test_signature_normalize_bool() -> None:
    s = SignatureStrategy()
    assert s.normalize(True) == {"present": True, "bbox": None}
    assert s.normalize(False) == {"present": False, "bbox": None}


def test_signature_normalize_dict_with_bbox() -> None:
    s = SignatureStrategy()
    assert s.normalize({"present": True, "bbox": [0.1, 0.2, 0.3, 0.4]}) == {
        "present": True,
        "bbox": (0.1, 0.2, 0.3, 0.4),
    }


def test_signature_normalize_string() -> None:
    s = SignatureStrategy()
    assert s.normalize("yes") == {"present": True, "bbox": None}
    assert s.normalize("no") == {"present": False, "bbox": None}


def test_signature_validate() -> None:
    s = SignatureStrategy()
    assert s.validate({"present": True}) == []
    assert s.validate(None) == ["required"]
    assert s.validate({}) == ["missing 'present' key"]
    assert s.validate({"present": "yes"}) == ["'present' must be bool"]


# ── List / Object strategies ────────────────────────────────────


def test_list_normalize_strings() -> None:
    s = ListStrategy()
    assert s.normalize([1, 2, 3]) == ["1", "2", "3"]


def test_list_normalize_invalid() -> None:
    s = ListStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("not a list")


def test_object_normalize() -> None:
    s = ObjectStrategy()
    assert s.normalize({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_object_normalize_invalid() -> None:
    s = ObjectStrategy()
    with pytest.raises(FieldValidationError):
        s.normalize("not an object")


# ── Factory + normalize_with_strategy ───────────────────────────


def test_get_strategy_known() -> None:
    assert isinstance(get_strategy("string"), StringStrategy)
    assert isinstance(get_strategy("number"), NumberStrategy)
    assert isinstance(get_strategy("boolean"), BooleanStrategy)
    assert isinstance(get_strategy("date"), DateStrategy)
    assert isinstance(get_strategy("currency"), CurrencyStrategy)
    assert isinstance(get_strategy("id"), IDStrategy)
    assert isinstance(get_strategy("address"), AddressStrategy)
    assert isinstance(get_strategy("table"), TableStrategy)
    assert isinstance(get_strategy("signature"), SignatureStrategy)
    assert isinstance(get_strategy("list"), ListStrategy)
    assert isinstance(get_strategy("object"), ObjectStrategy)


def test_get_strategy_unknown_falls_back_to_string() -> None:
    assert isinstance(get_strategy("not-a-kind"), StringStrategy)


def test_available_kinds() -> None:
    kinds = available_kinds()
    assert "string" in kinds
    assert "currency" in kinds
    assert "table" in kinds
    assert "signature" in kinds
    assert len(kinds) >= 10


def test_normalize_with_strategy_ok() -> None:
    value, errors = normalize_with_strategy("123", "number")
    assert value == 123
    assert errors == []


def test_normalize_with_strategy_invalid() -> None:
    _value, errors = normalize_with_strategy("not a number", "number")
    assert errors  # non-empty


# ── render_fields_block ─────────────────────────────────────────


def test_render_fields_block_basic() -> None:
    fields = [
        {"name": "vendor", "kind": "string", "description": "Vendor name"},
        {"name": "total", "kind": "currency"},
    ]
    out = render_fields_block(fields)
    assert "vendor" in out
    assert "total" in out
    assert "[string]" in out
    assert "[currency]" in out


def test_render_fields_block_handles_field_type_alias() -> None:
    fields = [{"name": "x", "field_type": "date"}]
    out = render_fields_block(fields)
    assert "[date]" in out
    assert "ISO 8601" in out
