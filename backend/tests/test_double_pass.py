"""Tests for the v0.5.0 double-pass self-correction module."""

from __future__ import annotations

import pytest

from app.services.extraction.double_pass import (
    EvidenceDiff,
    diff_evidence_maps,
    merge_with_dispute_explanation,
    needs_human_review,
)
from app.services.extraction.evidence import Evidence, EvidenceMap


def _ev(value: object, page: int = 0, score: float = 0.9, span: str = "x") -> Evidence:
    return Evidence(field="f", value=value, page=page, text_span=span, evidence_score=score)


# ── diff_evidence_maps ───────────────────────────────────────────


def test_diff_agreed_only() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme"), "b": _ev(100)})
    second = EvidenceMap(evidences={"a": _ev("Acme"), "b": _ev(100)})
    diff = diff_evidence_maps(first, second)
    assert diff.agreed == ["a", "b"]
    assert diff.disputed == []
    assert diff.only_in_first == []
    assert diff.only_in_second == []
    # "Empty" here means no disputes; agreement is OK.
    assert diff.is_empty() is True


def test_diff_disputed() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme")})
    second = EvidenceMap(evidences={"a": _ev("Globex")})
    diff = diff_evidence_maps(first, second)
    assert diff.disputed == ["a"]
    assert diff.agreed == []


def test_diff_only_in_one_pass() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme"), "b": _ev(100)})
    second = EvidenceMap(evidences={"a": _ev("Acme"), "c": _ev("extra")})
    diff = diff_evidence_maps(first, second)
    assert diff.agreed == ["a"]
    assert diff.only_in_first == ["b"]
    assert diff.only_in_second == ["c"]


def test_diff_string_normalization() -> None:
    """Trivial formatting differences are treated as agreement."""

    first = EvidenceMap(evidences={"a": _ev("Acme  Corp")})
    second = EvidenceMap(evidences={"a": _ev("acme corp")})
    diff = diff_evidence_maps(first, second)
    assert diff.agreed == ["a"]


def test_diff_numeric_tolerance() -> None:
    first = EvidenceMap(evidences={"a": _ev(100.0)})
    second = EvidenceMap(evidences={"a": _ev(100.0000001)})
    diff = diff_evidence_maps(first, second)
    assert diff.agreed == ["a"]


def test_diff_handles_missing_values() -> None:
    first = EvidenceMap(evidences={"a": _ev(None)})
    second = EvidenceMap(evidences={"a": _ev("value")})
    diff = diff_evidence_maps(first, second)
    assert diff.disputed == ["a"]


def test_diff_to_dict() -> None:
    diff = EvidenceDiff(agreed=["a"], disputed=["b"], only_in_first=["c"])
    d = diff.to_dict()
    assert d == {
        "agreed": ["a"],
        "disputed": ["b"],
        "only_in_first": ["c"],
        "only_in_second": [],
    }


# ── merge_with_dispute_explanation ──────────────────────────────


def test_merge_prefer_second() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme")})
    second = EvidenceMap(evidences={"a": _ev("Globex")})
    result = merge_with_dispute_explanation(first, second, prefer="second")
    assert result.evidence_map.get("a").value == "Globex"
    assert "a" in result.explanations


def test_merge_prefer_first() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme")})
    second = EvidenceMap(evidences={"a": _ev("Globex")})
    result = merge_with_dispute_explanation(first, second, prefer="first")
    assert result.evidence_map.get("a").value == "Acme"


def test_merge_prefer_both_routes_to_review() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme")})
    second = EvidenceMap(evidences={"a": _ev("Globex")})
    result = merge_with_dispute_explanation(first, second, prefer="both")
    assert "a" not in result.evidence_map.evidences
    assert "a" in result.evidence_map.not_found
    assert "a" in result.explanations


def test_merge_invalid_prefer() -> None:
    with pytest.raises(ValueError):
        merge_with_dispute_explanation(
            EvidenceMap(evidences={}), EvidenceMap(evidences={}), prefer="bogus"
        )


def test_merge_merges_not_found() -> None:
    first = EvidenceMap(evidences={"a": _ev("x")}, not_found=["b"])
    second = EvidenceMap(evidences={"a": _ev("x")}, not_found=["c"])
    result = merge_with_dispute_explanation(first, second, prefer="second")
    assert set(result.evidence_map.not_found) == {"b", "c"}


def test_merge_only_in_first() -> None:
    first = EvidenceMap(evidences={"a": _ev("x"), "b": _ev("only-first")})
    second = EvidenceMap(evidences={"a": _ev("x")})
    result = merge_with_dispute_explanation(first, second, prefer="second")
    assert "b" in result.evidence_map.evidences
    assert "b" in result.explanations


def test_merge_only_in_second() -> None:
    first = EvidenceMap(evidences={"a": _ev("x")})
    second = EvidenceMap(evidences={"a": _ev("x"), "b": _ev("only-second")})
    result = merge_with_dispute_explanation(first, second, prefer="second")
    assert "b" in result.evidence_map.evidences
    assert "b" in result.explanations


def test_merge_to_dict() -> None:
    first = EvidenceMap(evidences={"a": _ev("Acme")})
    second = EvidenceMap(evidences={"a": _ev("Acme")})
    result = merge_with_dispute_explanation(first, second)
    d = result.to_dict()
    assert "evidence_map" in d
    assert "diff" in d
    assert "explanations" in d


# ── _explain_dispute coverage ───────────────────────────────────


def test_explain_dispute_value_differs() -> None:
    first = EvidenceMap(evidences={"a": Evidence(field="a", value="x", page=0, text_span="x")})
    second = EvidenceMap(evidences={"a": Evidence(field="a", value="y", page=0, text_span="x")})
    result = merge_with_dispute_explanation(first, second)
    assert "value differs" in result.explanations["a"]


def test_explain_dispute_text_span_differs() -> None:
    first = EvidenceMap(evidences={"a": Evidence(field="a", value="x", page=0, text_span="span1")})
    second = EvidenceMap(evidences={"a": Evidence(field="a", value="x", page=0, text_span="span2")})
    result = merge_with_dispute_explanation(first, second)
    assert "text_span differs" in result.explanations["a"]


def test_explain_dispute_page_differs() -> None:
    first = EvidenceMap(evidences={"a": Evidence(field="a", value="x", page=0, text_span="x")})
    second = EvidenceMap(evidences={"a": Evidence(field="a", value="x", page=1, text_span="x")})
    result = merge_with_dispute_explanation(first, second)
    assert "page differs" in result.explanations["a"]


def test_explain_dispute_score_differs() -> None:
    first = EvidenceMap(
        evidences={"a": Evidence(field="a", value="x", page=0, text_span="x", evidence_score=0.5)}
    )
    second = EvidenceMap(
        evidences={"a": Evidence(field="a", value="x", page=0, text_span="x", evidence_score=0.9)}
    )
    result = merge_with_dispute_explanation(first, second)
    assert "score differs" in result.explanations["a"]


# ── needs_human_review ──────────────────────────────────────────


def test_needs_human_review_includes_disputed() -> None:
    diff = EvidenceDiff(disputed=["a"])
    assert needs_human_review(diff) == ["a"]


def test_needs_human_review_includes_only_in() -> None:
    diff = EvidenceDiff(only_in_first=["b"], only_in_second=["c"])
    out = needs_human_review(diff)
    assert set(out) == {"b", "c"}


def test_needs_human_review_empty() -> None:
    diff = EvidenceDiff(agreed=["a"])
    assert needs_human_review(diff) == []


def test_needs_human_review_dedups() -> None:
    diff = EvidenceDiff(disputed=["a"], only_in_first=["a"])
    assert needs_human_review(diff) == ["a"]
