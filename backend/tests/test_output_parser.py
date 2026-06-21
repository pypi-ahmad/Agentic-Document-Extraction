"""Tests for LLM output parser — JSON extraction and schema coercion."""

from __future__ import annotations

import pytest

from app.services.llm.output_parser import coerce_to_schema, parse_llm_json

# ── parse_llm_json: clean JSON ──────────────────────────────────────


def test_parse_clean_json():
    assert parse_llm_json('{"name": "Acme"}') == {"name": "Acme"}


def test_parse_clean_json_with_whitespace():
    assert parse_llm_json('  \n{"name": "Acme"}\n  ') == {"name": "Acme"}


# ── parse_llm_json: markdown fences ─────────────────────────────────


def test_parse_fenced_json():
    raw = '```json\n{"vendor": "Acme", "total": 100}\n```'
    assert parse_llm_json(raw) == {"vendor": "Acme", "total": 100}


def test_parse_fenced_no_lang():
    raw = '```\n{"vendor": "Acme"}\n```'
    assert parse_llm_json(raw) == {"vendor": "Acme"}


def test_parse_fenced_with_preamble():
    raw = 'Here is the extracted data:\n```json\n{"x": 1}\n```\nLet me know if you need more.'
    assert parse_llm_json(raw) == {"x": 1}


# ── parse_llm_json: preamble/postamble ──────────────────────────────


def test_parse_json_with_preamble():
    raw = 'Sure! Here is the extraction:\n{"vendor": "Acme", "total": 42.5}'
    assert parse_llm_json(raw) == {"vendor": "Acme", "total": 42.5}


def test_parse_json_with_postamble():
    raw = '{"vendor": "Acme"}\n\nI hope this helps!'
    assert parse_llm_json(raw) == {"vendor": "Acme"}


def test_parse_json_with_both():
    raw = 'Result:\n{"a": 1}\nEnd.'
    assert parse_llm_json(raw) == {"a": 1}


# ── parse_llm_json: trailing commas ──────────────────────────────────


def test_parse_trailing_comma_object():
    raw = '{"a": 1, "b": 2,}'
    assert parse_llm_json(raw) == {"a": 1, "b": 2}


def test_parse_trailing_comma_array():
    raw = '{"items": [1, 2, 3,]}'
    assert parse_llm_json(raw) == {"items": [1, 2, 3]}


def test_parse_trailing_comma_nested():
    raw = '{"a": {"b": 1,}, "c": [1,],}'
    assert parse_llm_json(raw) == {"a": {"b": 1}, "c": [1]}


# ── parse_llm_json: nested braces in text ────────────────────────────


def test_parse_nested_json_in_text():
    raw = 'The document mentions {invalid} data but here is the result: {"vendor": "Acme"}'
    # This should find the last valid JSON object
    result = parse_llm_json(raw)
    assert isinstance(result, dict)


# ── parse_llm_json: error cases ─────────────────────────────────────


def test_parse_empty_raises():
    with pytest.raises(ValueError, match="Empty"):
        parse_llm_json("")


def test_parse_whitespace_raises():
    with pytest.raises(ValueError, match="Empty"):
        parse_llm_json("   \n  ")


def test_parse_no_json_raises():
    with pytest.raises(ValueError, match="Could not extract"):
        parse_llm_json("No JSON here, just text.")


def test_parse_array_not_object_raises():
    """We only accept JSON objects (dicts), not arrays at the top level."""
    with pytest.raises(ValueError, match="Could not extract"):
        parse_llm_json("[1, 2, 3]")


def test_parse_incomplete_json_raises():
    with pytest.raises(ValueError, match="Could not extract"):
        parse_llm_json('{"name": "Acme", "total":')


# ── parse_llm_json: real-world LLM outputs ──────────────────────────


def test_parse_gemini_style():
    """Gemini sometimes returns JSON with leading newline inside fence."""
    raw = '```json\n\n{\n  "invoice_number": "INV-001",\n  "total": 1234.56\n}\n```'
    result = parse_llm_json(raw)
    assert result["invoice_number"] == "INV-001"
    assert result["total"] == 1234.56


def test_parse_chatgpt_conversational():
    """ChatGPT sometimes adds conversational text around the JSON."""
    raw = (
        "Based on the document, here is the extracted data:\n\n"
        '{"vendor": "Acme Corp", "date": "2024-01-15", "total": 500.00}\n\n'
        "Let me know if you need any changes!"
    )
    result = parse_llm_json(raw)
    assert result["vendor"] == "Acme Corp"


def test_parse_claude_thinking():
    """Claude sometimes includes thinking before the JSON."""
    raw = (
        "Let me analyze the document carefully.\n\n"
        "The invoice contains the following information:\n\n"
        '{"vendor": "Test Inc", "items": [{"name": "Widget", "price": 9.99}]}'
    )
    result = parse_llm_json(raw)
    assert result["vendor"] == "Test Inc"
    assert len(result["items"]) == 1


# ── coerce_to_schema: number ────────────────────────────────────────


def test_coerce_string_to_number():
    fields = [{"name": "total", "field_type": "number"}]
    assert coerce_to_schema({"total": "42.5"}, fields) == {"total": 42.5}


def test_coerce_string_int_to_number():
    fields = [{"name": "count", "field_type": "number"}]
    assert coerce_to_schema({"count": "7"}, fields) == {"count": 7}


def test_coerce_comma_number():
    fields = [{"name": "total", "field_type": "number"}]
    assert coerce_to_schema({"total": "1,234.56"}, fields) == {"total": 1234.56}


def test_coerce_already_number():
    fields = [{"name": "total", "field_type": "number"}]
    assert coerce_to_schema({"total": 42}, fields) == {"total": 42}


def test_coerce_number_null_passthrough():
    fields = [{"name": "total", "field_type": "number"}]
    assert coerce_to_schema({"total": None}, fields) == {"total": None}


# ── coerce_to_schema: boolean ───────────────────────────────────────


def test_coerce_string_true():
    fields = [{"name": "active", "field_type": "boolean"}]
    assert coerce_to_schema({"active": "true"}, fields) == {"active": True}


def test_coerce_string_yes():
    fields = [{"name": "active", "field_type": "boolean"}]
    assert coerce_to_schema({"active": "Yes"}, fields) == {"active": True}


def test_coerce_string_false():
    fields = [{"name": "active", "field_type": "boolean"}]
    assert coerce_to_schema({"active": "false"}, fields) == {"active": False}


def test_coerce_int_to_boolean():
    fields = [{"name": "active", "field_type": "boolean"}]
    assert coerce_to_schema({"active": 1}, fields) == {"active": True}


def test_coerce_already_boolean():
    fields = [{"name": "active", "field_type": "boolean"}]
    assert coerce_to_schema({"active": True}, fields) == {"active": True}


# ── coerce_to_schema: date ──────────────────────────────────────────


def test_coerce_iso_date():
    fields = [{"name": "date", "field_type": "date"}]
    assert coerce_to_schema({"date": "2024-01-15"}, fields) == {"date": "2024-01-15"}


def test_coerce_iso_datetime_to_date():
    fields = [{"name": "date", "field_type": "date"}]
    assert coerce_to_schema({"date": "2024-01-15T10:30:00"}, fields) == {"date": "2024-01-15"}


def test_coerce_us_date():
    fields = [{"name": "date", "field_type": "date"}]
    assert coerce_to_schema({"date": "01/15/2024"}, fields) == {"date": "2024-01-15"}


def test_coerce_us_date_single_digit():
    fields = [{"name": "date", "field_type": "date"}]
    assert coerce_to_schema({"date": "1/5/2024"}, fields) == {"date": "2024-01-05"}


# ── coerce_to_schema: list ──────────────────────────────────────────


def test_coerce_csv_to_list():
    fields = [{"name": "tags", "field_type": "list"}]
    assert coerce_to_schema({"tags": "a, b, c"}, fields) == {"tags": ["a", "b", "c"]}


def test_coerce_json_string_to_list():
    fields = [{"name": "tags", "field_type": "list"}]
    assert coerce_to_schema({"tags": '["a", "b"]'}, fields) == {"tags": ["a", "b"]}


def test_coerce_already_list():
    fields = [{"name": "tags", "field_type": "list"}]
    assert coerce_to_schema({"tags": [1, 2]}, fields) == {"tags": [1, 2]}


# ── coerce_to_schema: object ────────────────────────────────────────


def test_coerce_json_string_to_object():
    fields = [{"name": "meta", "field_type": "object"}]
    result = coerce_to_schema({"meta": '{"key": "val"}'}, fields)
    assert result == {"meta": {"key": "val"}}


def test_coerce_already_object():
    fields = [{"name": "meta", "field_type": "object"}]
    assert coerce_to_schema({"meta": {"k": 1}}, fields) == {"meta": {"k": 1}}


# ── coerce_to_schema: string ────────────────────────────────────────


def test_coerce_number_to_string():
    fields = [{"name": "code", "field_type": "string"}]
    assert coerce_to_schema({"code": 42}, fields) == {"code": "42"}


def test_coerce_bool_to_string():
    fields = [{"name": "flag", "field_type": "string"}]
    assert coerce_to_schema({"flag": True}, fields) == {"flag": "True"}


# ── coerce_to_schema: edge cases ────────────────────────────────────


def test_coerce_unknown_fields_dropped():
    """Fields not declared in the schema are removed from workflow output."""
    fields = [{"name": "vendor", "field_type": "string"}]
    result = coerce_to_schema({"vendor": "Acme", "extra": 123}, fields)
    assert result == {"vendor": "Acme"}


def test_coerce_unconvertible_keeps_original():
    """If coercion fails, the original value is kept."""
    fields = [{"name": "total", "field_type": "number"}]
    result = coerce_to_schema({"total": "not a number"}, fields)
    assert result == {"total": "not a number"}


def test_coerce_empty_schema():
    """No schema fields means no declared output fields survive."""
    assert coerce_to_schema({"a": 1}, []) == {}


def test_coerce_empty_data():
    fields = [{"name": "x", "field_type": "number"}]
    assert coerce_to_schema({}, fields) == {}


def test_coerce_multiple_fields():
    fields = [
        {"name": "vendor", "field_type": "string"},
        {"name": "total", "field_type": "number"},
        {"name": "date", "field_type": "date"},
        {"name": "paid", "field_type": "boolean"},
    ]
    data = {"vendor": "Acme", "total": "1,500", "date": "03/15/2024", "paid": "yes"}
    result = coerce_to_schema(data, fields)
    assert result == {
        "vendor": "Acme",
        "total": 1500,
        "date": "2024-03-15",
        "paid": True,
    }
