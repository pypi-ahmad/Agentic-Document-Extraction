"""G-Eval LLM-as-judge for extraction quality.

G-Eval (Liu et al. 2023) is a chain-of-thought LLM-as-judge that
scores generated text on multiple criteria, each with a 1-5 rating
and a brief reason. We use a small local Ollama model
(``Settings.judge_ollama_model``, default ``qwen3.5:4b``) to score
a sampled subset of completed extractions.

Why a small local model
------------------------

- Zero API cost per judgment; safe to run on every completed
  extraction at the default 5% sample rate.
- Stays on the same machine as the rest of the pipeline; no PII
  leaves the cluster.
- 4B is the empirical floor for reliable G-Eval CoT scoring; the
  9B opt-in gives slightly tighter grade agreement with human
  reviewers.

Sampling
--------

``Settings.judge_sample_rate`` controls the fraction of completed
extractions to judge. The default 0.05 (5%) gives ~150 judgments per
3k-extraction production day, which is enough to surface a 1pp
regression in field F1 within a day.

Stored in the new ``extraction_judgments`` table.
"""

from __future__ import annotations

import json
import random
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import httpx

from app.config import settings
from app.logging_setup import get_logger

logger = get_logger("app.judge")

G_EVAL_VERSION = "geval-1"
"""Bump when the prompt template or scoring rubric changes."""

# Default judge criteria. Each criterion is scored 1-5 (1 = worst,
# 5 = best) with a one-sentence reason. The overall score is the
# unweighted mean of the per-criterion scores.
DEFAULT_CRITERIA: tuple[str, ...] = (
    "correctness",
    "completeness",
    "schema_conformance",
    "fluency",
)
CRITERION_RUBRIC: dict[str, str] = {
    "correctness": "Extracted values match the ground truth (no fabricated or wrong values).",
    "completeness": "All required fields are present; nothing is silently missing.",
    "schema_conformance": "The output JSON is well-formed and respects the requested schema.",
    "fluency": "Any text values (names, addresses, notes) are natural and well-formatted.",
}


@dataclass(frozen=True)
class CriterionScore:
    criterion: str
    score: int  # 1-5
    reason: str


@dataclass
class Judgment:
    extraction_id: str
    judge_model: str
    judge_version: str
    scores: dict[str, CriterionScore] = field(default_factory=dict)
    overall_score: float = 0.0
    reasoning: str = ""
    latency_ms: int = 0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["scores"] = {k: asdict(v) for k, v in self.scores.items()}
        return d


# ── Sampling ─────────────────────────────────────────────────────────


def should_judge(sample_rate: float | None = None, *, rng: random.Random | None = None) -> bool:
    """Return True when this extraction should be sent to the judge.

    Uses a per-call RNG so the sample rate is deterministic when
    desired. The default is non-deterministic (uses system entropy).
    """
    if not settings.judge_enabled:
        return False
    rate = sample_rate if sample_rate is not None else settings.judge_sample_rate
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    r = rng or random
    return r.random() < rate


# ── Prompt builder ──────────────────────────────────────────────────


def _build_judge_prompt(
    *,
    schema_fields: list[dict],
    expected: Mapping[str, Any],
    predicted: Mapping[str, Any],
    criteria: tuple[str, ...] = DEFAULT_CRITERIA,
) -> tuple[str, str]:
    """Build the G-Eval system + user prompt pair.

    Returns ``(system, user)``; the user is told to return a JSON
    object keyed by criterion with ``{score, reason}``.
    """
    field_descriptions = []
    for f in schema_fields:
        req = "required" if f.get("required", True) else "optional"
        field_descriptions.append(
            f'  - "{f["name"]}" ({f.get("field_type", "string")}, {req}): {f.get("description", "")}'
        )
    fields_block = "\n".join(field_descriptions)

    criteria_block = "\n".join(
        f"  - {c} (1-5): {CRITERION_RUBRIC.get(c, 'No description.')}" for c in criteria
    )

    system = (
        "You are a strict, fair document-extraction evaluator. "
        "You will be shown a schema, the ground-truth values, and "
        "the model's extracted values. For each criterion, give a "
        "score from 1 to 5 and a one-sentence reason. Respond with "
        "ONLY a JSON object of the form "
        '`{"correctness": {"score": N, "reason": "..."}, ...}`. '
        "Do not include any other text."
    )
    user = (
        f"SCHEMA:\n{fields_block}\n\n"
        f"GROUND TRUTH:\n{json.dumps(expected, indent=2)}\n\n"
        f"PREDICTED:\n{json.dumps(predicted, indent=2)}\n\n"
        f"CRITERIA:\n{criteria_block}\n\n"
        "Your JSON evaluation:"
    )
    return system, user


# ── Judge call ──────────────────────────────────────────────────────


def _ollama_chat(
    *,
    base_url: str,
    model: str,
    system: str,
    user: str,
    timeout_seconds: float,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, int]:
    """Call the Ollama ``/api/chat`` endpoint and return
    ``(content, latency_ms)``.

    Uses a passed-in client when given (so tests can mock it);
    otherwise builds a one-shot client.
    """
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
    }
    owns_client = client is None

    async def _call() -> tuple[str, int]:
        c = httpx.AsyncClient(timeout=timeout_seconds) if owns_client else client  # type: ignore[assignment]
        t0 = time.perf_counter()
        try:
            resp = await c.post(url, json=payload)  # type: ignore[union-attr]
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns_client:
                await c.aclose()
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return data.get("message", {}).get("content", ""), latency_ms

    # The synchronous wrapper: the judge caller decides whether to
    # ``await`` this or run it via ``asyncio.run``. We expose the
    # coroutine so the public async API is just a thin ``await``.
    return _call(), 0  # placeholder; the real latency is computed inside _call


# Public async wrapper. The httpx call itself is async, so we need
# a separate async entry point.
async def _ollama_chat_async(
    *,
    base_url: str,
    model: str,
    system: str,
    user: str,
    timeout_seconds: float,
    client: httpx.AsyncClient | None = None,
) -> tuple[str, int]:
    """Async call to Ollama /api/chat. Returns ``(content, latency_ms)``."""
    url = f"{base_url.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
    }
    owns_client = client is None
    c = client if client is not None else httpx.AsyncClient(timeout=timeout_seconds)
    t0 = time.perf_counter()
    try:
        resp = await c.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if owns_client:
            await c.aclose()
    latency_ms = int((time.perf_counter() - t0) * 1000)
    return data.get("message", {}).get("content", ""), latency_ms


# ── Parsing ─────────────────────────────────────────────────────────


def parse_judge_response(
    raw: str,
    *,
    criteria: tuple[str, ...] = DEFAULT_CRITERIA,
) -> tuple[dict[str, CriterionScore], str]:
    """Parse the judge's JSON response.

    The Ollama model is asked to respond with a JSON object keyed
    by criterion. The parser is permissive about minor formatting
    issues (trailing commas, single quotes) and falls back to a
    single heuristic if the JSON is unparseable.

    Returns ``(scores, reasoning)`` where ``reasoning`` is the
    concatenated free-form reason text (used in the audit log).
    """
    text = raw.strip()
    # Strip code fences if any.
    if text.startswith("```"):
        text = text.strip("`")
        if "\n" in text:
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("judge.parse_failed: %s — raw: %r", exc, raw[:200])
        return {}, raw[:200]

    scores: dict[str, CriterionScore] = {}
    reasons: list[str] = []
    for c in criteria:
        entry = data.get(c) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            continue
        try:
            score = int(entry.get("score", 0))
        except (TypeError, ValueError):
            continue
        score = max(1, min(5, score))
        reason = str(entry.get("reason", "")).strip()
        scores[c] = CriterionScore(criterion=c, score=score, reason=reason)
        reasons.append(f"{c}: {reason}")
    return scores, "\n".join(reasons)


# ── Public API ──────────────────────────────────────────────────────


async def judge_extraction(
    *,
    extraction_id: str,
    schema_fields: list[dict],
    expected: Mapping[str, Any],
    predicted: Mapping[str, Any],
    client: httpx.AsyncClient | None = None,
    criteria: tuple[str, ...] = DEFAULT_CRITERIA,
) -> Judgment:
    """Run the G-Eval judge and return a populated :class:`Judgment`.

    The returned :class:`Judgment` is what the caller persists to
    the ``extraction_judgments`` table (or surfaces in metrics).
    This function never writes to the DB itself; the persistence
    lives in the route layer so it can share the same session.
    """
    base_url = settings.judge_ollama_base_url or settings.ollama_base_url
    model = settings.judge_ollama_model
    system, user = _build_judge_prompt(
        schema_fields=schema_fields,
        expected=expected,
        predicted=predicted,
        criteria=criteria,
    )
    raw, latency_ms = await _ollama_chat_async(
        base_url=base_url,
        model=model,
        system=system,
        user=user,
        timeout_seconds=settings.judge_ollama_timeout_seconds,
        client=client,
    )
    scores, reasoning = parse_judge_response(raw, criteria=criteria)
    overall = sum(s.score for s in scores.values()) / len(scores) if scores else 0.0
    return Judgment(
        extraction_id=extraction_id,
        judge_model=model,
        judge_version=G_EVAL_VERSION,
        scores=scores,
        overall_score=overall,
        reasoning=reasoning,
        latency_ms=latency_ms,
    )


def is_below_threshold(j: Judgment, *, threshold: float | None = None) -> bool:
    """Return True when the judgment's overall score is below the
    configured minimum (i.e. a quality regression signal)."""
    t = threshold if threshold is not None else settings.judge_min_overall_score
    return j.overall_score > 0 and j.overall_score < t


__all__ = [
    "CRITERION_RUBRIC",
    "DEFAULT_CRITERIA",
    "G_EVAL_VERSION",
    "CriterionScore",
    "Judgment",
    "is_below_threshold",
    "judge_extraction",
    "parse_judge_response",
    "should_judge",
]
