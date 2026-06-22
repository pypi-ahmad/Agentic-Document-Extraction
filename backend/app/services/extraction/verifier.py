"""Independent verifier for v0.5.0 evidence-grounded extraction.

A verifier is a small model (typically different from the
extractor) that re-checks each field's evidence against the
document. The conflict resolver flags disagreed-upon fields
for human review.

Public API
----------

* :class:`Verdict` — the verifier's per-field judgment.
* :class:`BaseVerifier` — ABC.
* :class:`NoOpVerifier` — always agrees; used in tests + when
  ``enable_verifier`` is False.
* :class:`LLMVerifier` — calls a local Ollama model to verify.
* :func:`resolve_disputes` — turns a verifier verdict map into
  a list of disputed field names.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.services.extraction.evidence import Evidence, EvidenceMap

logger = logging.getLogger(__name__)


VERDICT_VALUES: tuple[str, ...] = ("agree", "disagree", "unsure")


def _normalize_verdict(value: str | None) -> str:
    """Coerce a free-form verdict label to one of ``VERDICT_VALUES``."""

    if not value:
        return "unsure"
    lowered = value.strip().lower()
    # Check longer verdicts first so "disagree" does not match "agree".
    for v in sorted(VERDICT_VALUES, key=len, reverse=True):
        if v in lowered:
            return v
    return "unsure"


# ── Verdict dataclass ───────────────────────────────────────────────


@dataclass(frozen=True)
class Verdict:
    """Verifier judgment on a single field."""

    field: str
    verdict: str  # "agree" | "disagree" | "unsure"
    reason: str = ""
    suggested_value: Any = None
    confidence: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "verdict", _normalize_verdict(self.verdict))
        if self.confidence < 0.0:
            object.__setattr__(self, "confidence", 0.0)
        elif self.confidence > 1.0:
            object.__setattr__(self, "confidence", 1.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason": self.reason,
            "suggested_value": self.suggested_value,
            "confidence": self.confidence,
        }


@dataclass
class VerifierOutput:
    """Full output of a verifier run on one extraction."""

    field_verdicts: dict[str, Verdict] = field(default_factory=dict)
    overall_agreement: float = 1.0
    latency_ms: int = 0

    def disputed_fields(self) -> list[str]:
        return [f for f, v in self.field_verdicts.items() if v.verdict == "disagree"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "field_verdicts": {k: v.to_dict() for k, v in self.field_verdicts.items()},
            "overall_agreement": self.overall_agreement,
            "latency_ms": self.latency_ms,
            "disputed_fields": self.disputed_fields(),
        }


# ── Base verifier ───────────────────────────────────────────────────


class BaseVerifier(ABC):
    """Interface every verifier must implement."""

    name: str = "base"

    @abstractmethod
    async def verify(
        self,
        evidence_map: EvidenceMap,
        document_text: str,
        *,
        schema_fields: list[str] | None = None,
    ) -> VerifierOutput:
        """Verify the evidence map against the document text."""


# ── NoOp verifier (default for tests + opt-out) ────────────────────


class NoOpVerifier(BaseVerifier):
    """Verifier that always agrees.

    Used in tests and when the user has set
    ``enable_verifier=False``. The pipeline treats the NoOp
    verifier as a passthrough: no fields are flagged.
    """

    name = "noop"

    async def verify(
        self,
        evidence_map: EvidenceMap,
        document_text: str,
        *,
        schema_fields: list[str] | None = None,
    ) -> VerifierOutput:
        return VerifierOutput(field_verdicts={}, overall_agreement=1.0, latency_ms=0)


# ── Deterministic verifier (no LLM) ────────────────────────────────


class HeuristicVerifier(BaseVerifier):
    """A verifier that does not call any LLM.

    Heuristics:
    * If the text_span is not contained in the document text,
      the field is flagged "disagree" (low confidence in the
      evidence).
    * If the evidence_score is < 0.6, the field is flagged
      "unsure".
    * Otherwise "agree".

    This is the default verifier when ``enable_verifier=True`` and
    no LLM verifier is configured. It runs in O(N) over the
    fields and adds negligible latency.
    """

    name = "heuristic"
    low_score_threshold: float = 0.6
    min_evidence_score: float = 0.5

    async def verify(
        self,
        evidence_map: EvidenceMap,
        document_text: str,
        *,
        schema_fields: list[str] | None = None,
    ) -> VerifierOutput:
        verdicts: dict[str, Verdict] = {}
        agree_count = 0
        for fname, ev in evidence_map.evidences.items():
            verdict = self._check_field(ev, document_text)
            verdicts[fname] = verdict
            if verdict.verdict == "agree":
                agree_count += 1
        total = len(verdicts)
        # Empty map → vacuously agree (no disputes to resolve)
        agreement = 1.0 if total == 0 else agree_count / total
        return VerifierOutput(
            field_verdicts=verdicts,
            overall_agreement=agreement,
        )

    def _check_field(self, ev: Evidence, document_text: str) -> Verdict:
        text_span = (ev.text_span or "").strip()
        if not text_span:
            return Verdict(
                field=ev.field,
                verdict="disagree",
                reason="no text_span in evidence",
                confidence=0.0,
            )
        if text_span in document_text:
            found = True
            ci = False
        elif text_span.lower() in document_text.lower():
            found = True
            ci = True
        else:
            found = False
            ci = False
        if not found:
            return Verdict(
                field=ev.field,
                verdict="disagree",
                reason=f"text_span not found in document: {text_span[:60]!r}",
                confidence=0.0,
            )
        if ev.evidence_score < self.low_score_threshold:
            return Verdict(
                field=ev.field,
                verdict="unsure",
                reason=f"low evidence_score={ev.evidence_score:.2f}",
                confidence=ev.evidence_score,
            )
        if ci:
            return Verdict(
                field=ev.field,
                verdict="agree",
                reason="text_span found (case-insensitive)",
                confidence=min(1.0, ev.evidence_score * 0.9),
            )
        return Verdict(
            field=ev.field,
            verdict="agree",
            reason="text_span present and score above threshold",
            confidence=ev.evidence_score,
        )


# ── LLM verifier (Ollama) ──────────────────────────────────────────


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_verifier_response(text: str) -> dict[str, Any] | None:
    """Parse the LLM verifier's JSON response."""

    if not text:
        return None
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    match = _JSON_BLOCK.search(stripped)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


class LLMVerifier(BaseVerifier):
    """Verifier backed by a local Ollama chat model.

    The verifier prompt is deliberately small — the LLM is only
    asked to confirm or refute each field's evidence against the
    document text. The default model is the same one used by the
    G-Eval judge (``qwen3.5:4b``); a separate, larger model can be
    configured for production use.
    """

    name = "llm"

    def __init__(
        self,
        *,
        model: str = "qwen3.5:4b",
        base_url: str = "http://localhost:11434",
        timeout_seconds: float = 60.0,
    ) -> None:
        self.model = model
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    async def verify(
        self,
        evidence_map: EvidenceMap,
        document_text: str,
        *,
        schema_fields: list[str] | None = None,
    ) -> VerifierOutput:
        import asyncio
        import time

        if not evidence_map.evidences:
            return VerifierOutput(field_verdicts={}, overall_agreement=1.0, latency_ms=0)

        prompt = self._build_prompt(evidence_map, document_text, schema_fields)
        start = time.monotonic()
        try:
            raw = await asyncio.wait_for(
                self._call_ollama(prompt),
                timeout=self.timeout_seconds,
            )
        except (TimeoutError, Exception) as exc:
            logger.warning("LLM verifier call failed: %s", exc)
            return VerifierOutput(
                field_verdicts={},
                overall_agreement=0.0,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        return self._parse_output(raw, latency_ms)

    async def _call_ollama(self, prompt: str) -> str:
        import httpx

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout_seconds
        ) as client:
            response = await client.post(
                "/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            response.raise_for_status()
            data = response.json()
        return data.get("response", "")

    def _build_prompt(
        self,
        evidence_map: EvidenceMap,
        document_text: str,
        schema_fields: list[str] | None,
    ) -> str:
        field_lines: list[str] = []
        for fname, ev in evidence_map.evidences.items():
            field_lines.append(
                f"- {fname} = {ev.value!r} | text_span = {ev.text_span!r} | score = {ev.evidence_score}"
            )
        fields_block = "\n".join(field_lines) if field_lines else "(none)"
        return (
            "You are an independent verifier. For each field, decide whether the "
            "cited text_span actually appears in the document and supports the value.\n\n"
            f"FIELDS:\n{fields_block}\n\n"
            f"DOCUMENT (truncated to 4000 chars):\n{document_text[:4000]}\n\n"
            'Output ONLY JSON: {"verdicts": {"field": {"verdict": '
            '"agree"|"disagree"|"unsure", "reason": "...", '
            '"confidence": 0.0-1.0}}}.'
        )

    def _parse_output(self, raw: str, latency_ms: int) -> VerifierOutput:
        parsed = _parse_verifier_response(raw)
        if not parsed:
            return VerifierOutput(field_verdicts={}, overall_agreement=0.0, latency_ms=latency_ms)
        verdicts_raw = parsed.get("verdicts", {})
        verdicts: dict[str, Verdict] = {}
        if isinstance(verdicts_raw, dict):
            for field, defn in verdicts_raw.items():
                if not isinstance(defn, dict):
                    continue
                verdicts[field] = Verdict(
                    field=field,
                    verdict=_normalize_verdict(defn.get("verdict")),
                    reason=str(defn.get("reason", "")).strip(),
                    suggested_value=defn.get("suggested_value"),
                    confidence=float(defn.get("confidence", 0.0) or 0.0),
                )
        agree_count = sum(1 for v in verdicts.values() if v.verdict == "agree")
        total = max(1, len(verdicts))
        return VerifierOutput(
            field_verdicts=verdicts,
            overall_agreement=agree_count / total,
            latency_ms=latency_ms,
        )


# ── Conflict resolution ────────────────────────────────────────────


def resolve_disputes(
    output: VerifierOutput,
    *,
    on_disagree: str = "human_review",
) -> list[str]:
    """Turn a verifier output into a list of disputed field names.

    Args:
        output: The verifier output.
        on_disagree: How to handle "disagree" verdicts. Currently
            only ``"human_review"`` is supported; disputed fields
            are returned as a list.
    """

    if on_disagree == "human_review":
        return output.disputed_fields()
    if on_disagree == "ignore":
        return []
    raise ValueError(f"Unknown on_disagree strategy: {on_disagree!r}")


# ── Factory ────────────────────────────────────────────────────────


def get_default_verifier(*, enable_llm: bool = False) -> BaseVerifier:
    """Return the default verifier for the current configuration."""

    if not enable_llm:
        return HeuristicVerifier()
    return LLMVerifier()
