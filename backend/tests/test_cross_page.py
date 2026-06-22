"""Tests for the v0.5.0 cross-page entity resolver."""

from __future__ import annotations

import pytest

from app.services.extraction.cross_page import (
    EntityMention,
    EntityTracker,
    ResolvedEntity,
    jaccard,
    mentions_from_evidence,
    resolve_entities,
    tokenize,
)
from app.services.extraction.evidence import Evidence, EvidenceMap

# ── tokenize / jaccard ──────────────────────────────────────────────


def test_tokenize_basic() -> None:
    assert tokenize("Acme Corp") == {"acme", "corp"}


def test_tokenize_drops_stopwords() -> None:
    assert "the" not in tokenize("The Acme Corp of Delaware")
    assert "of" not in tokenize("The Acme Corp of Delaware")
    assert "acme" in tokenize("The Acme Corp of Delaware")


def test_tokenize_empty() -> None:
    assert tokenize("") == set()
    assert tokenize("   ") == set()


def test_tokenize_punctuation() -> None:
    assert tokenize("Acme, Inc.") == {"acme", "inc"}


def test_jaccard_identical() -> None:
    assert jaccard({"a", "b"}, {"a", "b"}) == 1.0


def test_jaccard_disjoint() -> None:
    assert jaccard({"a", "b"}, {"c", "d"}) == 0.0


def test_jaccard_partial() -> None:
    # a intersect b = 1, a union b = 3 -> 1/3
    assert jaccard({"a", "b"}, {"a", "c"}) == pytest.approx(1 / 3)


def test_jaccard_empty() -> None:
    assert jaccard(set(), set()) == 1.0
    assert jaccard({"a"}, set()) == 0.0
    assert jaccard(set(), {"a"}) == 0.0


# ── EntityMention / ResolvedEntity ─────────────────────────────────


def test_entity_mention_to_dict() -> None:
    m = EntityMention(text="Acme", page=0, bbox=(0.1, 0.1, 0.4, 0.2))
    d = m.to_dict()
    assert d["text"] == "Acme"
    assert d["page"] == 0
    assert d["bbox"] == [0.1, 0.1, 0.4, 0.2]


def test_resolved_entity_to_dict() -> None:
    e = ResolvedEntity(
        entity_type="org",
        canonical_form="Acme Corp",
        mentions=[EntityMention(text="Acme Corp", page=0)],
        confidence=0.9,
    )
    d = e.to_dict()
    assert d["canonical_form"] == "Acme Corp"
    assert d["entity_type"] == "org"
    assert d["confidence"] == 0.9
    assert len(d["mentions"]) == 1


def test_resolved_entity_add_mention() -> None:
    e = ResolvedEntity(entity_type="org", canonical_form="Acme")
    e.add_mention(EntityMention(text="Acme", page=0))
    e.add_mention(EntityMention(text="Acme", page=1))
    assert len(e.mentions) == 2


# ── EntityTracker ──────────────────────────────────────────────────


def _mention(text: str, page: int = 0) -> EntityMention:
    return EntityMention(text=text, page=page)


def test_tracker_single_mention() -> None:
    t = EntityTracker()
    out = t.cluster_mentions([_mention("Acme Corp")])
    assert len(out) == 1
    assert out[0].canonical_form == "Acme Corp"
    assert out[0].confidence == 0.9


def test_tracker_identical_mentions_cluster() -> None:
    t = EntityTracker()
    out = t.cluster_mentions(
        [
            _mention("Acme Corp", page=0),
            _mention("Acme Corp", page=1),
            _mention("Acme Corp", page=2),
        ]
    )
    assert len(out) == 1
    assert out[0].canonical_form == "Acme Corp"
    assert len(out[0].mentions) == 3


def test_tracker_abbreviation_clusters_with_full_form() -> None:
    t = EntityTracker(jaccard_threshold=0.3)
    out = t.cluster_mentions(
        [
            _mention("Acme Corp", page=0),
            _mention("Acme", page=1),
        ]
    )
    assert len(out) == 1
    # Longest non-abbreviation wins
    assert out[0].canonical_form == "Acme Corp"


def test_tracker_short_string_does_not_cluster() -> None:
    t = EntityTracker(min_mention_length=3)
    out = t.cluster_mentions([_mention("AB"), _mention("AC")])
    assert len(out) == 0


def test_tracker_disjoint_mentions_split() -> None:
    t = EntityTracker()
    out = t.cluster_mentions(
        [
            _mention("Acme Corp", page=0),
            _mention("Globex Inc", page=1),
        ]
    )
    assert len(out) == 2
    forms = {e.canonical_form for e in out}
    assert forms == {"Acme Corp", "Globex Inc"}


def test_tracker_threshold_filters_weak_matches() -> None:
    t = EntityTracker(jaccard_threshold=0.9)
    out = t.cluster_mentions(
        [
            _mention("Acme Corp", page=0),
            _mention("Acme Incorporated", page=1),
        ]
    )
    # Token sets: {acme,corp} vs {acme,incorporated} → jaccard = 1/3
    # Below 0.9 → split
    assert len(out) == 2


def test_tracker_invalid_threshold() -> None:
    with pytest.raises(ValueError):
        EntityTracker(jaccard_threshold=1.5)
    with pytest.raises(ValueError):
        EntityTracker(jaccard_threshold=-0.1)


def test_tracker_invalid_min_length() -> None:
    with pytest.raises(ValueError):
        EntityTracker(min_mention_length=0)


def test_tracker_picks_longest_canonical_form() -> None:
    t = EntityTracker()
    out = t.cluster_mentions(
        [
            _mention("Acme", page=0),
            _mention("Acme Corp", page=1),
            _mention("Acme Corporation", page=2),
        ]
    )
    assert len(out) == 1
    # Longest is "Acme Corporation" but "Acme Corp" has highest
    # length-and-frequency score? Actually we score by length;
    # ties broken by frequency. "Acme Corporation" is the longest.
    assert out[0].canonical_form == "Acme Corporation"


def test_tracker_penalizes_single_letter_abbreviation() -> None:
    t = EntityTracker()
    out = t.cluster_mentions(
        [
            _mention("Ac", page=0),  # short abbreviation, penalized
            _mention("Acme Corp", page=1),
        ]
    )
    # jaccard of {ac} vs {acme,corp} is 0 → no cluster
    assert len(out) == 2
    canonical_forms = {e.canonical_form for e in out}
    assert canonical_forms == {"Ac", "Acme Corp"}


# ── resolve_entities convenience ──────────────────────────────────


def test_resolve_entities_basic() -> None:
    out = resolve_entities(
        [
            _mention("Acme Corp", page=0),
            _mention("Acme", page=1),
        ],
        entity_type="org",
        jaccard_threshold=0.3,
    )
    assert len(out) == 1
    assert out[0].entity_type == "org"


# ── mentions_from_evidence ────────────────────────────────────────


def test_mentions_from_evidence_with_predicate() -> None:
    m = EvidenceMap(
        evidences={
            "vendor": Evidence(
                field="vendor",
                value="Acme Corp",
                page=0,
                text_span="Acme Corp",
                evidence_score=0.9,
            ),
            "total": Evidence(
                field="total",
                value=100.0,
                page=0,
                text_span="$100",
                evidence_score=0.9,
            ),
        },
    )
    mentions = mentions_from_evidence(m, text_field_predicate=lambda f: f == "vendor")
    assert len(mentions) == 1
    assert mentions[0].text == "Acme Corp"
    assert mentions[0].field == "vendor"


def test_mentions_from_evidence_no_predicate() -> None:
    m = EvidenceMap(
        evidences={
            "vendor": Evidence(field="vendor", value="Acme", page=0, text_span="Acme"),
            "total": Evidence(field="total", value=100.0, page=0, text_span="$100"),
        },
    )
    mentions = mentions_from_evidence(m)
    # Only string-typed values become mentions
    assert len(mentions) == 1
    assert mentions[0].text == "Acme"


def test_mentions_from_evidence_empty_map() -> None:
    m = EvidenceMap(evidences={})
    assert mentions_from_evidence(m) == []


def test_mentions_from_evidence_invalid_input() -> None:
    # Pass a non-EvidenceMap; the adapter should return [] gracefully
    assert mentions_from_evidence({}) == []  # type: ignore[arg-type]
    assert mentions_from_evidence(None) == []  # type: ignore[arg-type]
