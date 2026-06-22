"""Double-pass self-correction (v0.5.0).

When ``enable_double_pass`` is True, the reflect node runs the
extractor twice with different seeds and forces an explanation
of any diff. Disputed fields are routed to ``needs_human_review``.

This is a deterministic post-processor: it takes two
:class:`EvidenceMap` objects (the two extraction passes) and
returns the merged evidence map plus a list of disputed
fields. The actual LLM calls are made elsewhere; this module
just decides what to do with the diff.

Public API
----------

* :func:`diff_evidence_maps` — compute the diff between two maps.
* :func:`merge_with_dispute_explanation` — merge two maps and
  explain each dispute.
* :func:`needs_human_review` — fields that should be escalated
  to a human reviewer given the diff.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.extraction.evidence import Evidence, EvidenceMap

# ── Diff result ──────────────────────────────────────────────────


@dataclass
class EvidenceDiff:
    """The diff between two :class:`EvidenceMap` objects."""

    agreed: list[str] = field(default_factory=list)
    """Fields where the two maps produced the same value."""

    disputed: list[str] = field(default_factory=list)
    """Fields where the two maps produced different values."""

    only_in_first: list[str] = field(default_factory=list)
    """Fields present in ``first`` but not in ``second``."""

    only_in_second: list[str] = field(default_factory=list)
    """Fields present in ``second`` but not in ``first``."""

    def is_empty(self) -> bool:
        return not (self.disputed or self.only_in_first or self.only_in_second)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agreed": list(self.agreed),
            "disputed": list(self.disputed),
            "only_in_first": list(self.only_in_first),
            "only_in_second": list(self.only_in_second),
        }


# ── Diff function ───────────────────────────────────────────────


def diff_evidence_maps(first: EvidenceMap, second: EvidenceMap) -> EvidenceDiff:
    """Compute the diff between two :class:`EvidenceMap` objects.

    The two maps are compared field-by-field. Fields are
    "agreed" if both the value AND the evidence metadata
    (text_span, page, score) match; "disputed" if anything
    differs; "only in first/second" if the field is in one but
    not the other.
    """

    first_fields = set(first.fields())
    second_fields = set(second.fields())

    only_in_first = sorted(first_fields - second_fields)
    only_in_second = sorted(second_fields - first_fields)
    common = first_fields & second_fields

    agreed: list[str] = []
    disputed: list[str] = []
    for f in sorted(common):
        ev1 = first.get(f)
        ev2 = second.get(f)
        if ev1 is None and ev2 is None:
            agreed.append(f)
            continue
        if ev1 is None or ev2 is None:
            disputed.append(f)
            continue
        if _evidence_equivalent(ev1, ev2):
            agreed.append(f)
        else:
            disputed.append(f)

    return EvidenceDiff(
        agreed=agreed,
        disputed=disputed,
        only_in_first=only_in_first,
        only_in_second=only_in_second,
    )


def _evidence_equivalent(a: Evidence, b: Evidence) -> bool:
    """Return True if two Evidence objects match on value and metadata."""

    if not _values_equivalent(a.value, b.value):
        return False
    if _normalize_str(a.text_span or "") != _normalize_str(b.text_span or ""):
        return False
    if a.page != b.page:
        return False
    return abs(a.evidence_score - b.evidence_score) <= 1e-6


def _values_equivalent(a: Any, b: Any) -> bool:
    """Compare two extracted values, ignoring trivial formatting differences."""

    if a == b:
        return True
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return _normalize_str(a) == _normalize_str(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-6
    return False


def _normalize_str(s: str) -> str:
    """Normalize a string for equivalence comparison."""

    return " ".join(s.split()).strip().lower()


# ── Merge with explanation ──────────────────────────────────────


@dataclass
class MergeResult:
    """The merged evidence map + per-dispute explanations."""

    evidence_map: EvidenceMap
    diff: EvidenceDiff
    explanations: dict[str, str] = field(default_factory=dict)
    """Per-disputed-field explanation: ``{field: reason}``."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_map": self.evidence_map.to_dict(),
            "diff": self.diff.to_dict(),
            "explanations": dict(self.explanations),
        }


def merge_with_dispute_explanation(
    first: EvidenceMap,
    second: EvidenceMap,
    *,
    prefer: str = "second",
) -> MergeResult:
    """Merge two evidence maps and explain disputes.

    Args:
        first: The first extraction's evidence map.
        second: The second extraction's evidence map.
        prefer: Which map to use for disputed fields. ``"second"``
            (default) trusts the second pass; ``"first"`` trusts the
            first; ``"both"`` keeps both and routes to human review.

    The explanations are produced locally (no LLM call) by
    computing a structural diff of the two ``Evidence`` objects.
    When the user has access to the v2/reflection.md prompt, the
    LLM is asked for a richer ``diff_explanation`` and the
    returned text replaces the local one.
    """

    if prefer not in {"first", "second", "both"}:
        raise ValueError(f"Unknown prefer strategy: {prefer!r}")

    diff = diff_evidence_maps(first, second)
    explanations: dict[str, str] = {}

    # Build the merged evidence map
    merged_evidences: dict[str, Evidence] = {}
    merged_not_found: list[str] = list({*first.not_found, *second.not_found})

    for fname in diff.agreed:
        # Use the first one (they're equivalent)
        ev = first.get(fname) or second.get(fname)
        if ev is not None:
            merged_evidences[fname] = ev

    if prefer == "both":
        # Route disputed to human review; do not add to merged_evidences
        for fname in diff.disputed:
            explanations[fname] = _explain_dispute(first.get(fname), second.get(fname))
            if fname not in merged_not_found:
                merged_not_found.append(fname)
        for fname in diff.only_in_first + diff.only_in_second:
            if fname not in merged_not_found:
                merged_not_found.append(fname)
    else:
        primary = second if prefer == "second" else first
        for fname in diff.disputed:
            ev = primary.get(fname)
            if ev is not None:
                merged_evidences[fname] = ev
            explanations[fname] = _explain_dispute(first.get(fname), second.get(fname))
        for fname in diff.only_in_first:
            ev = first.get(fname)
            if ev is not None:
                merged_evidences[fname] = ev
            explanations[fname] = f"present in first pass only: {fname}"
        for fname in diff.only_in_second:
            ev = second.get(fname)
            if ev is not None:
                merged_evidences[fname] = ev
            explanations[fname] = f"present in second pass only: {fname}"

    merged_map = EvidenceMap(
        evidences=merged_evidences,
        not_found=sorted(set(merged_not_found)),
    )
    return MergeResult(evidence_map=merged_map, diff=diff, explanations=explanations)


def _explain_dispute(first: Evidence | None, second: Evidence | None) -> str:
    """Build a local explanation of a dispute between two evidence objects."""

    if first is None and second is None:
        return "both passes missing"
    if first is None:
        return f"only second pass produced: {second.value!r} (page {second.page})"
    if second is None:
        return f"only first pass produced: {first.value!r} (page {first.page})"
    parts: list[str] = []
    if first.value != second.value:
        parts.append(f"value differs: {first.value!r} vs {second.value!r}")
    if first.text_span != second.text_span:
        parts.append(f"text_span differs: {first.text_span!r} vs {second.text_span!r}")
    if first.page != second.page:
        parts.append(f"page differs: {first.page} vs {second.page}")
    if first.evidence_score != second.evidence_score:
        parts.append(f"score differs: {first.evidence_score:.2f} vs {second.evidence_score:.2f}")
    if not parts:
        return "structural diff only"
    return "; ".join(parts)


# ── Human review trigger ────────────────────────────────────────


def needs_human_review(diff: EvidenceDiff) -> list[str]:
    """Return the field names that should be escalated to a human reviewer.

    Any disputed or asymmetric (only-in-one-pass) field is
    escalated. The v0.4.0 confidence-threshold logic is
    orthogonal: this function only returns fields where the
    two passes disagreed, regardless of confidence.
    """

    return sorted(set(diff.disputed + diff.only_in_first + diff.only_in_second))
