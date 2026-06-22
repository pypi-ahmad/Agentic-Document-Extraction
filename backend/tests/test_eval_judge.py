"""Unit tests for the G-Eval LLM-as-judge module.

Covers the sampling logic, the prompt builder, the JSON parser, the
``is_below_threshold`` helper, and the end-to-end ``judge_extraction``
flow with a mocked Ollama HTTP client.
"""

from __future__ import annotations

import json
import random
from typing import Any

import httpx
import pytest

from app.services.eval.judge import (
    CRITERION_RUBRIC,
    DEFAULT_CRITERIA,
    G_EVAL_VERSION,
    CriterionScore,
    Judgment,
    _build_judge_prompt,
    is_below_threshold,
    judge_extraction,
    parse_judge_response,
    should_judge,
)

# ── should_judge ─────────────────────────────────────────────────────


def test_should_judge_disabled_via_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.judge_enabled", False)
    monkeypatch.setattr("app.config.settings.judge_sample_rate", 1.0)
    assert should_judge() is False


def test_should_judge_rate_zero_never_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.judge_enabled", True)
    monkeypatch.setattr("app.config.settings.judge_sample_rate", 0.0)
    assert should_judge() is False


def test_should_judge_rate_one_always_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.judge_enabled", True)
    monkeypatch.setattr("app.config.settings.judge_sample_rate", 1.0)
    assert should_judge() is True


def test_should_judge_uses_deterministic_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    """When given an RNG, the decision is reproducible."""
    monkeypatch.setattr("app.config.settings.judge_enabled", True)
    monkeypatch.setattr("app.config.settings.judge_sample_rate", 0.5)
    rng = random.Random(0)
    sampled_in = sum(1 for _ in range(1000) if should_judge(rng=rng))
    # Approximately half should be sampled. With seed 0 this is
    # deterministic; we just check it is in the [400, 600] range.
    assert 400 < sampled_in < 600


# ── _build_judge_prompt ─────────────────────────────────────────────


def test_build_judge_prompt_includes_fields_and_ground_truth() -> None:
    system, user = _build_judge_prompt(
        schema_fields=[
            {"name": "vendor", "field_type": "string", "required": True},
            {"name": "total", "field_type": "number", "required": True},
        ],
        expected={"vendor": "Acme", "total": 500},
        predicted={"vendor": "Acme", "total": 500},
    )
    assert "evaluator" in system.lower()
    assert "JSON" in user
    assert "vendor" in user
    assert "Acme" in user
    assert "500" in user
    # The four default criteria should be listed.
    for c in DEFAULT_CRITERIA:
        assert c in user
        assert c in CRITERION_RUBRIC


# ── parse_judge_response ────────────────────────────────────────────


def test_parse_judge_response_perfect() -> None:
    raw = json.dumps(
        {
            "correctness": {"score": 5, "reason": "exact match"},
            "completeness": {"score": 5, "reason": "all fields present"},
            "schema_conformance": {"score": 5, "reason": "valid json"},
            "fluency": {"score": 5, "reason": "natural"},
        }
    )
    scores, reasoning = parse_judge_response(raw)
    assert set(scores) == set(DEFAULT_CRITERIA)
    for s in scores.values():
        assert s.score == 5
    assert "correctness: exact match" in reasoning


def test_parse_judge_response_clamps_to_1_5() -> None:
    raw = json.dumps(
        {
            "correctness": {"score": 99, "reason": "out of range"},
            "completeness": {"score": 0, "reason": "out of range"},
            "schema_conformance": {"score": 3, "reason": "ok"},
            "fluency": {"score": 3, "reason": "ok"},
        }
    )
    scores, _ = parse_judge_response(raw)
    assert scores["correctness"].score == 5  # clamped up
    assert scores["completeness"].score == 1  # clamped down


def test_parse_judge_response_strips_code_fence() -> None:
    raw = (
        "```json\n"
        + json.dumps(
            {
                "correctness": {"score": 4, "reason": "ok"},
                "completeness": {"score": 4, "reason": "ok"},
                "schema_conformance": {"score": 4, "reason": "ok"},
                "fluency": {"score": 4, "reason": "ok"},
            }
        )
        + "\n```"
    )
    scores, _ = parse_judge_response(raw)
    assert scores["correctness"].score == 4


def test_parse_judge_response_handles_invalid_json() -> None:
    scores, reasoning = parse_judge_response("not json at all")
    assert scores == {}
    assert "not json" in reasoning


def test_parse_judge_response_ignores_missing_criteria() -> None:
    raw = json.dumps({"correctness": {"score": 4, "reason": "ok"}})
    scores, _ = parse_judge_response(raw)
    assert set(scores) == {"correctness"}


def test_parse_judge_response_ignores_non_dict_entry() -> None:
    raw = json.dumps({"correctness": "not a dict"})
    scores, _ = parse_judge_response(raw)
    assert scores == {}


# ── judge_extraction end-to-end with mocked HTTP ────────────────────


class _MockTransport(httpx.AsyncBaseTransport):
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.response_payload = response_payload
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return httpx.Response(200, json=self.response_payload)


@pytest.mark.asyncio
async def test_judge_extraction_returns_judgment(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: mock Ollama, run judge_extraction, assert the result."""
    monkeypatch.setattr("app.config.settings.judge_enabled", True)
    monkeypatch.setattr("app.config.settings.judge_ollama_base_url", "http://mock-ollama:11434")
    monkeypatch.setattr("app.config.settings.judge_ollama_model", "qwen3.5:4b")
    monkeypatch.setattr("app.config.settings.judge_ollama_timeout_seconds", 10.0)

    mock_payload = {
        "message": {
            "content": json.dumps(
                {
                    "correctness": {"score": 4, "reason": "good"},
                    "completeness": {"score": 5, "reason": "complete"},
                    "schema_conformance": {"score": 4, "reason": "ok"},
                    "fluency": {"score": 5, "reason": "natural"},
                }
            )
        }
    }
    transport = _MockTransport(mock_payload)
    client = httpx.AsyncClient(transport=transport, base_url="http://mock-ollama:11434")

    j = await judge_extraction(
        extraction_id="ext-123",
        schema_fields=[
            {"name": "vendor", "field_type": "string", "required": True},
            {"name": "total", "field_type": "number", "required": True},
        ],
        expected={"vendor": "Acme", "total": 500},
        predicted={"vendor": "Acme", "total": 500},
        client=client,
    )
    await client.aclose()

    assert j.extraction_id == "ext-123"
    assert j.judge_model == "qwen3.5:4b"
    assert j.judge_version == G_EVAL_VERSION
    assert j.overall_score == pytest.approx(4.5)
    assert set(j.scores) == set(DEFAULT_CRITERIA)
    # The transport captured the request; verify it hit the right URL.
    assert transport.last_request is not None
    assert "/api/chat" in str(transport.last_request.url)


@pytest.mark.asyncio
async def test_judge_extraction_handles_unparseable_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A garbage response yields an overall_score of 0 and no scores."""
    monkeypatch.setattr("app.config.settings.judge_ollama_base_url", "http://mock-ollama:11434")
    monkeypatch.setattr("app.config.settings.judge_ollama_model", "qwen3.5:4b")

    mock_payload = {"message": {"content": "garbage not json"}}
    transport = _MockTransport(mock_payload)
    client = httpx.AsyncClient(transport=transport, base_url="http://mock-ollama:11434")

    j = await judge_extraction(
        extraction_id="ext-456",
        schema_fields=[],
        expected={},
        predicted={},
        client=client,
    )
    await client.aclose()
    assert j.overall_score == 0.0
    assert j.scores == {}


# ── is_below_threshold ──────────────────────────────────────────────


def test_is_below_threshold_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.config.settings.judge_min_overall_score", 3.5)
    assert is_below_threshold(
        Judgment(extraction_id="x", judge_model="m", judge_version="geval-1", overall_score=3.0)
    )
    assert not is_below_threshold(
        Judgment(extraction_id="x", judge_model="m", judge_version="geval-1", overall_score=4.0)
    )


def test_is_below_threshold_zero_is_never_flagged() -> None:
    """overall_score=0 means the judge failed; don't flag it as low-quality."""
    j = Judgment(extraction_id="x", judge_model="m", judge_version="geval-1", overall_score=0.0)
    assert not is_below_threshold(j, threshold=5.0)


def test_is_below_threshold_explicit_threshold() -> None:
    j = Judgment(extraction_id="x", judge_model="m", judge_version="geval-1", overall_score=2.5)
    assert is_below_threshold(j, threshold=3.0)
    assert not is_below_threshold(j, threshold=2.0)


# ── Judgment roundtrip ──────────────────────────────────────────────


def test_judgment_to_dict_serializes_scores() -> None:
    j = Judgment(
        extraction_id="x",
        judge_model="m",
        judge_version="geval-1",
        scores={"correctness": CriterionScore("correctness", 5, "ok")},
        overall_score=5.0,
    )
    d = j.to_dict()
    assert d["scores"]["correctness"] == {
        "criterion": "correctness",
        "score": 5,
        "reason": "ok",
    }
    assert d["overall_score"] == 5.0
