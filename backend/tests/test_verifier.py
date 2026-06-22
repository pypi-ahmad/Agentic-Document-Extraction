"""Tests for the v0.5.0 verifier + conflict resolver."""

from __future__ import annotations

import asyncio

import pytest

from app.services.extraction.evidence import Evidence, EvidenceMap
from app.services.extraction.verifier import (
    HeuristicVerifier,
    LLMVerifier,
    NoOpVerifier,
    Verdict,
    VerifierOutput,
    _parse_verifier_response,
    get_default_verifier,
    resolve_disputes,
)

# ── Verdict dataclass ───────────────────────────────────────────────


def test_verdict_normalizes_known_values() -> None:
    v = Verdict(field="x", verdict="AGREE", reason="ok", confidence=0.5)
    assert v.verdict == "agree"


def test_verdict_unsure_for_unknown() -> None:
    v = Verdict(field="x", verdict="gibberish")
    assert v.verdict == "unsure"


def test_verdict_clamps_confidence() -> None:
    v1 = Verdict(field="x", verdict="agree", confidence=2.0)
    assert v1.confidence == 1.0
    v2 = Verdict(field="x", verdict="agree", confidence=-0.5)
    assert v2.confidence == 0.0


def test_verdict_to_dict() -> None:
    v = Verdict(field="x", verdict="agree", reason="ok", confidence=0.9)
    d = v.to_dict()
    assert d == {"verdict": "agree", "reason": "ok", "suggested_value": None, "confidence": 0.9}


# ── VerifierOutput ──────────────────────────────────────────────────


def test_verifier_output_disputed_fields() -> None:
    o = VerifierOutput(
        field_verdicts={
            "a": Verdict(field="a", verdict="agree"),
            "b": Verdict(field="b", verdict="disagree"),
            "c": Verdict(field="c", verdict="unsure"),
        },
        overall_agreement=1 / 3,
    )
    assert o.disputed_fields() == ["b"]


def test_verifier_output_to_dict() -> None:
    o = VerifierOutput(
        field_verdicts={"a": Verdict(field="a", verdict="agree")},
        overall_agreement=1.0,
        latency_ms=42,
    )
    d = o.to_dict()
    assert d["field_verdicts"]["a"]["verdict"] == "agree"
    assert d["overall_agreement"] == 1.0
    assert d["latency_ms"] == 42
    assert d["disputed_fields"] == []


# ── NoOpVerifier ───────────────────────────────────────────────────


def test_noop_verifier_agrees() -> None:
    v = NoOpVerifier()
    m = EvidenceMap(
        evidences={"a": Evidence(field="a", value=1, page=0, text_span="1")},
    )
    out = asyncio.run(v.verify(m, "doc"))
    assert out.overall_agreement == 1.0
    assert out.field_verdicts == {}


# ── HeuristicVerifier ───────────────────────────────────────────────


def test_heuristic_verifier_agrees_on_present_text() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(
        evidences={
            "a": Evidence(
                field="a", value="Acme", page=0, text_span="Acme Corp", evidence_score=0.9
            ),
        },
    )
    out = asyncio.run(v.verify(m, "Acme Corp invoice 123"))
    assert out.field_verdicts["a"].verdict == "agree"


def test_heuristic_verifier_agrees_on_case_insensitive_match() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value="acme", page=0, text_span="ACME", evidence_score=0.9),
        },
    )
    out = asyncio.run(v.verify(m, "Acme Corp invoice"))
    assert out.field_verdicts["a"].verdict == "agree"


def test_heuristic_verifier_disagrees_on_missing_text() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value="X", page=0, text_span="NotInDoc", evidence_score=0.9),
        },
    )
    out = asyncio.run(v.verify(m, "Hello world"))
    assert out.field_verdicts["a"].verdict == "disagree"


def test_heuristic_verifier_unsure_on_low_score() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value="X", page=0, text_span="Hello", evidence_score=0.4),
        },
    )
    out = asyncio.run(v.verify(m, "Hello world"))
    assert out.field_verdicts["a"].verdict == "unsure"


def test_heuristic_verifier_disagrees_on_empty_text_span() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value="X", page=0, text_span=""),
        },
    )
    out = asyncio.run(v.verify(m, "Hello world"))
    assert out.field_verdicts["a"].verdict == "disagree"


def test_heuristic_verifier_aggregates_agreement() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value="1", page=0, text_span="Hello", evidence_score=0.9),
            "b": Evidence(field="b", value="2", page=0, text_span="Goodbye", evidence_score=0.9),
        },
    )
    out = asyncio.run(v.verify(m, "Hello world"))
    assert out.overall_agreement == 0.5
    assert "b" in out.disputed_fields()


def test_heuristic_verifier_empty_map() -> None:
    v = HeuristicVerifier()
    m = EvidenceMap(evidences={})
    out = asyncio.run(v.verify(m, "anything"))
    assert out.overall_agreement == 1.0
    assert out.disputed_fields() == []


# ── resolve_disputes ───────────────────────────────────────────────


def test_resolve_disputes_human_review() -> None:
    o = VerifierOutput(
        field_verdicts={
            "a": Verdict(field="a", verdict="disagree"),
            "b": Verdict(field="b", verdict="agree"),
        },
    )
    assert resolve_disputes(o) == ["a"]


def test_resolve_disputes_ignore() -> None:
    o = VerifierOutput(
        field_verdicts={"a": Verdict(field="a", verdict="disagree")},
    )
    assert resolve_disputes(o, on_disagree="ignore") == []


def test_resolve_disputes_unknown_strategy() -> None:
    o = VerifierOutput(field_verdicts={})
    with pytest.raises(ValueError):
        resolve_disputes(o, on_disagree="made_up")


# ── LLMVerifier unit tests (no real LLM call) ─────────────────────


def test_llm_verifier_returns_empty_on_empty_map() -> None:
    v = LLMVerifier()
    m = EvidenceMap(evidences={})
    out = asyncio.run(v.verify(m, "doc"))
    assert out.overall_agreement == 1.0
    assert out.field_verdicts == {}


def test_llm_verifier_prompt_contains_fields() -> None:
    v = LLMVerifier()
    m = EvidenceMap(
        evidences={
            "vendor": Evidence(
                field="vendor", value="Acme", page=0, text_span="Acme", evidence_score=0.9
            ),
        },
    )
    prompt = v._build_prompt(m, "document text", None)
    assert "vendor" in prompt
    assert "Acme" in prompt
    assert "document text"[:100] in prompt


def test_parse_verifier_response_valid() -> None:
    raw = '{"verdicts": {"x": {"verdict": "agree", "reason": "ok", "confidence": 0.9}}}'
    parsed = _parse_verifier_response(raw)
    assert parsed["verdicts"]["x"]["verdict"] == "agree"


def test_parse_verifier_response_with_garbage() -> None:
    raw = 'Here is the result:\n{"verdicts": {"x": {"verdict": "disagree"}}}\nDone.'
    parsed = _parse_verifier_response(raw)
    assert parsed["verdicts"]["x"]["verdict"] == "disagree"


def test_parse_verifier_response_invalid() -> None:
    assert _parse_verifier_response("not json") is None
    assert _parse_verifier_response("") is None


def test_llm_verifier_parses_valid_output() -> None:
    v = LLMVerifier()
    raw = '{"verdicts": {"a": {"verdict": "agree", "reason": "ok", "confidence": 0.8}}}'
    out = v._parse_output(raw, latency_ms=10)
    assert out.field_verdicts["a"].verdict == "agree"
    assert out.overall_agreement == 1.0


def test_llm_verifier_handles_invalid_output() -> None:
    v = LLMVerifier()
    out = v._parse_output("garbage", latency_ms=5)
    assert out.overall_agreement == 0.0
    assert out.field_verdicts == {}


# ── get_default_verifier factory ───────────────────────────────────


def test_get_default_verifier_heuristic() -> None:
    v = get_default_verifier(enable_llm=False)
    assert isinstance(v, HeuristicVerifier)


def test_get_default_verifier_llm() -> None:
    v = get_default_verifier(enable_llm=True)
    assert isinstance(v, LLMVerifier)
    assert v.model == "qwen3.5:4b"
