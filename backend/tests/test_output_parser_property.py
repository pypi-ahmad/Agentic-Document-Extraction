"""Property-based tests for the LLM output parser and schema coercer.

These exercise the same surface as the example-based tests in
``test_output_parser.py`` but with fuzzed inputs. The point is to
catch edge cases (weird whitespace, deeply nested structures, mixed
quote styles, big numbers, dates) that hand-written tests miss.
"""

from __future__ import annotations

import json
import string

import hypothesis.strategies as st
from hypothesis import given, settings

from app.services.llm.output_parser import (
    coerce_to_schema,
    extract_confidence,
    parse_llm_json,
)

# ── Hypothesis strategies ───────────────────────────────────────────


_json_value: st.SearchStrategy[object] = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**31), max_value=2**31),
        st.floats(allow_nan=False, allow_infinity=False, width=32),
        st.text(max_size=80),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=10),
        st.dictionaries(
            keys=st.text(alphabet=string.ascii_letters, min_size=1, max_size=20),
            values=children,
            max_size=10,
        ),
    ),
    max_leaves=50,
)

_field_strategies: st.SearchStrategy[dict] = st.dictionaries(
    keys=st.sampled_from(["name", "total", "date", "active", "items", "meta"]),
    values=st.sampled_from(
        [
            {"name": "string", "field_type": "string", "required": True},
            {"name": "total", "field_type": "number", "required": True},
            {"name": "date", "field_type": "date", "required": True},
            {"name": "active", "field_type": "boolean", "required": True},
            {"name": "items", "field_type": "list", "required": True},
            {"name": "meta", "field_type": "object", "required": True},
        ]
    ),
    min_size=1,
    max_size=6,
)


# ── parse_llm_json: round-trip ────────────────────────────────────────


_json_dict: st.SearchStrategy[dict] = st.dictionaries(
    keys=st.text(alphabet=string.ascii_letters, min_size=1, max_size=20),
    values=st.recursive(
        st.one_of(
            st.none(),
            st.booleans(),
            st.integers(min_value=-(2**31), max_value=2**31),
            st.floats(allow_nan=False, allow_infinity=False, width=32),
            st.text(max_size=80),
        ),
        lambda children: st.one_of(
            st.lists(children, max_size=10),
            st.dictionaries(
                keys=st.text(alphabet=string.ascii_letters, min_size=1, max_size=20),
                values=children,
                max_size=10,
            ),
        ),
        max_leaves=50,
    ),
    min_size=0,
    max_size=10,
)


@given(_json_dict)
@settings(max_examples=200, deadline=None)
def test_parse_llm_json_round_trip(value: dict) -> None:
    """Any dict-shaped JSON should round-trip through parse_llm_json."""
    raw = json.dumps(value)
    parsed = parse_llm_json(raw)
    assert parsed == value


@given(st.text(min_size=1, max_size=200).filter(lambda s: "{" not in s and "[" not in s))
@settings(max_examples=50, deadline=None)
def test_parse_llm_json_text_only_raises(raw: str) -> None:
    """Plain text with no JSON structure must raise."""
    import pytest

    with pytest.raises(ValueError):
        parse_llm_json(raw)


# ── coerce_to_schema: idempotence on already-typed values ──────────


@given(
    _json_value,
    st.sampled_from(["string", "number", "boolean", "date", "list", "object"]),
)
@settings(max_examples=200, deadline=None)
def test_coerce_to_schema_is_idempotent(value: object, field_type: str) -> None:
    """Coercing an already-correct value should return the same value (or its
    closest legal representation for that type)."""
    fields = [{"name": "x", "field_type": field_type, "required": True}]
    data = {"x": value}
    first = coerce_to_schema(data, fields)
    second = coerce_to_schema(first, fields)
    assert first == second


# ── coerce_to_schema: drops unknown fields ──────────────────────────


@given(
    st.dictionaries(
        keys=st.sampled_from(["x", "y", "z", "extra1", "extra2"]),
        values=st.sampled_from([1, "a", True, None]),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=100, deadline=None)
def test_coerce_to_schema_drops_unknown_fields(data: dict) -> None:
    """Fields not in the schema are dropped."""
    fields = [{"name": "x", "field_type": "string", "required": True}]
    result = coerce_to_schema(data, fields)
    assert set(result.keys()).issubset({"x"})


# ── extract_confidence: round-trip on the clean_data ────────────────


@given(
    st.dictionaries(
        keys=st.sampled_from(["a", "b", "c", "_confidence"]),
        values=st.one_of(
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            st.floats(min_value=-5.0, max_value=5.0, allow_nan=False),
            st.text(),
            st.none(),
            st.integers(),
        ),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=200, deadline=None)
def test_extract_confidence_does_not_crash(data: dict) -> None:
    clean, conf = extract_confidence(dict(data))
    # Whatever the input, the output _confidence key must be gone.
    assert "_confidence" not in clean
    # Every confidence entry is a float in [0, 1].
    for v in conf.values():
        assert isinstance(v, float)
        assert 0.0 <= v <= 1.0
