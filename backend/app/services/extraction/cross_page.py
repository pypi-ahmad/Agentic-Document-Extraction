"""Cross-page entity resolution (v0.5.0).

When a document spans multiple pages, the same logical entity
(person, organization, address, account number, ...) often
appears in multiple forms on different pages:

* abbreviated ("Acme Corp" / "Acme" / "A. Corp")
* repeated in a table header on every page
* referenced across pages ("see page 3 for details")
* split across lines ("Acme\nCorp Inc.")

The cross-page resolver finds all mentions of each canonical
entity and emits a single canonical form with a list of
mentions (page, bbox, text_span, region_id).

Implementation
--------------

We use a Jaccard-similarity approach on token sets:

* Tokenize each candidate string (whitespace + lowercased).
* Compare token sets using Jaccard similarity.
* Cluster candidates with similarity >= ``jaccard_threshold``.
* Pick the canonical form as the longest non-abbreviated form
  in the cluster (or the most frequent one as a tiebreaker).

This is O(N^2) over the candidates, but N is small per
extraction (typically <100 unique entity strings), so it's
fine in practice. For very large documents a union-find
implementation would be needed.

Public API
----------

* :class:`EntityMention` — a single occurrence of an entity.
* :class:`ResolvedEntity` — canonical form + cluster of mentions.
* :class:`EntityTracker` — main entry point.
* :func:`resolve_entities` — convenience function.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# Stopwords that should not be counted when clustering entity strings.
_DEFAULT_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "in",
        "on",
        "at",
        "to",
        "for",
        "by",
        "with",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        # Note: company suffixes (inc, llc, corp, ...) are kept
        # because they're significant for entity disambiguation.
    }
)

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
# Common abbreviations that often signal a continuation, e.g. "Inc.".
_ABBREVIATION_RE = re.compile(r"^[A-Z]\.?$|^Inc\.?$|^Corp\.?$|^Ltd\.?$|^LLC\.?$|^Co\.?$")


def tokenize(text: str, *, stopwords: frozenset[str] = _DEFAULT_STOPWORDS) -> set[str]:
    """Lowercase + split a string into significant tokens."""

    if not text:
        return set()
    tokens = {m.group(0).lower() for m in _WORD_RE.finditer(text)}
    return {t for t in tokens if t and t not in stopwords}


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""

    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


# ── Mention + ResolvedEntity ────────────────────────────────────────


@dataclass(frozen=True)
class EntityMention:
    """A single occurrence of an entity in the document."""

    text: str
    page: int
    bbox: tuple[float, float, float, float] | None = None
    region_id: str | None = None
    field: str | None = None
    """Optional: which extracted field the mention came from."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "region_id": self.region_id,
            "field": self.field,
        }


@dataclass
class ResolvedEntity:
    """A canonical entity with a cluster of mentions."""

    entity_type: str
    canonical_form: str
    mentions: list[EntityMention] = field(default_factory=list)
    confidence: float = 0.0

    def add_mention(self, mention: EntityMention) -> None:
        self.mentions.append(mention)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_type": self.entity_type,
            "canonical_form": self.canonical_form,
            "mentions": [m.to_dict() for m in self.mentions],
            "confidence": self.confidence,
        }


# ── EntityTracker ──────────────────────────────────────────────────


class EntityTracker:
    """Cluster entity mentions across pages.

    Args:
        jaccard_threshold: Minimum Jaccard similarity to merge
            two candidates. Default 0.5 is conservative.
        min_mention_length: Skip mentions shorter than this.
    """

    def __init__(
        self,
        *,
        jaccard_threshold: float = 0.5,
        min_mention_length: int = 2,
    ) -> None:
        if not 0.0 <= jaccard_threshold <= 1.0:
            raise ValueError("jaccard_threshold must be in [0, 1]")
        if min_mention_length < 1:
            raise ValueError("min_mention_length must be >= 1")
        self.jaccard_threshold = jaccard_threshold
        self.min_mention_length = min_mention_length

    def cluster_mentions(
        self, mentions: Iterable[EntityMention], *, entity_type: str = "generic"
    ) -> list[ResolvedEntity]:
        """Cluster mentions into ResolvedEntity objects."""

        candidates: list[tuple[EntityMention, set[str]]] = []
        for m in mentions:
            text = (m.text or "").strip()
            if len(text) < self.min_mention_length:
                continue
            tokens = tokenize(text)
            # Single-letter mentions survive tokenization even if the
            # single letter is a stopword; we still want to cluster
            # them so "A" and "Acme" can be considered together.
            if not tokens and len(text) >= 1:
                tokens = {text.lower()}
            if not tokens:
                continue
            candidates.append((m, tokens))

        # Union-find clustering on candidates
        parent = list(range(len(candidates)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                if jaccard(candidates[i][1], candidates[j][1]) >= self.jaccard_threshold:
                    union(i, j)

        # Group candidates by root
        clusters: dict[int, list[int]] = {}
        for i in range(len(candidates)):
            root = find(i)
            clusters.setdefault(root, []).append(i)

        # Build ResolvedEntity for each cluster
        out: list[ResolvedEntity] = []
        for indices in clusters.values():
            cluster_mentions = [candidates[i][0] for i in indices]
            canonical = self._pick_canonical_form(cluster_mentions)
            confidence = self._cluster_confidence(cluster_mentions, candidates)
            resolved = ResolvedEntity(
                entity_type=entity_type,
                canonical_form=canonical,
                mentions=cluster_mentions,
                confidence=confidence,
            )
            out.append(resolved)
        return out

    def _pick_canonical_form(self, mentions: list[EntityMention]) -> str:
        """Pick the canonical form for a cluster.

        Heuristic: prefer the longest mention that does not end in a
        single-letter abbreviation. On tie, prefer the most frequent.
        """

        texts = [m.text for m in mentions if m.text]
        if not texts:
            return ""
        counter = Counter(texts)
        # Score: (length, frequency). Higher is better.
        scored: list[tuple[int, int, str]] = []
        for text, count in counter.items():
            length_score = len(text)
            # Penalize single-letter abbreviations
            if _ABBREVIATION_RE.match(text.strip()):
                length_score -= 5
            scored.append((length_score, count, text))
        scored.sort(reverse=True)
        return scored[0][2]

    def _cluster_confidence(
        self,
        cluster_mentions: list[EntityMention],
        all_candidates: list[tuple[EntityMention, set[str]]],
    ) -> float:
        """Confidence that the cluster is a single entity.

        1.0 for a single-mention cluster; approaches 1.0 for a
        multi-mention cluster where all members have identical
        text; lower for heterogeneous clusters.
        """

        if not cluster_mentions:
            return 0.0
        if len(cluster_mentions) == 1:
            return 0.9
        texts = [m.text for m in cluster_mentions]
        counter = Counter(texts)
        most_common_count = counter.most_common(1)[0][1]
        return min(1.0, most_common_count / len(texts))


# ── Convenience function ───────────────────────────────────────────


def resolve_entities(
    mentions: Iterable[EntityMention],
    *,
    entity_type: str = "generic",
    jaccard_threshold: float = 0.5,
) -> list[ResolvedEntity]:
    """Cluster ``mentions`` and return one :class:`ResolvedEntity` per cluster."""

    tracker = EntityTracker(jaccard_threshold=jaccard_threshold)
    return tracker.cluster_mentions(mentions, entity_type=entity_type)


# ── Adapter: build mentions from an EvidenceMap ────────────────────


def mentions_from_evidence(
    evidence_map: Any,
    *,
    text_field_predicate: callable | None = None,
) -> list[EntityMention]:
    """Convert an :class:`EvidenceMap` into entity mentions.

    The optional ``text_field_predicate`` is called with each
    field name and returns True if the field is a "named entity"
    (e.g. ``vendor``, ``customer``, ``account_holder``). If
    omitted, every field is treated as a candidate.
    """

    from app.services.extraction.evidence import EvidenceMap  # avoid circular

    if not isinstance(evidence_map, EvidenceMap):
        return []
    out: list[EntityMention] = []
    for fname, ev in evidence_map.evidences.items():
        if text_field_predicate is not None and not text_field_predicate(fname):
            continue
        value = ev.value
        if not isinstance(value, str):
            continue
        out.append(
            EntityMention(
                text=value,
                page=ev.page,
                bbox=ev.bbox,
                region_id=ev.source_region_id,
                field=fname,
            )
        )
    return out
