"""Tests for the v0.5.0 evidence module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.extraction.evidence import (
    Evidence,
    EvidenceMap,
    bbox_iou,
    build_evidence_map,
    filter_low_evidence,
    load_evidence_map,
    merge_with_not_found,
    page_locality_correct,
    save_evidence_map,
)

# ── Bbox parsing / IoU ──────────────────────────────────────────────


def test_bbox_iou_identical() -> None:
    a = (0.1, 0.1, 0.5, 0.5)
    assert bbox_iou(a, a) == pytest.approx(1.0)


def test_bbox_iou_disjoint() -> None:
    a = (0.0, 0.0, 0.2, 0.2)
    b = (0.8, 0.8, 1.0, 1.0)
    assert bbox_iou(a, b) == 0.0


def test_bbox_iou_partial_overlap() -> None:
    a = (0.0, 0.0, 0.5, 0.5)
    b = (0.25, 0.25, 0.75, 0.75)
    # inter = 0.25*0.25 = 0.0625; area_a = 0.25; area_b = 0.25; union = 0.4375
    # iou = 0.0625 / 0.4375 = 0.142857...
    assert bbox_iou(a, b) == pytest.approx(0.142857, rel=1e-3)


def test_bbox_iou_none_inputs() -> None:
    assert bbox_iou(None, (0, 0, 0.5, 0.5)) == 0.0
    assert bbox_iou((0, 0, 0.5, 0.5), None) == 0.0
    assert bbox_iou(None, None) == 0.0


def test_bbox_iou_degenerate_box() -> None:
    # x1 == x0 → degenerate
    a = (0.1, 0.1, 0.1, 0.5)
    b = (0.1, 0.1, 0.5, 0.5)
    assert bbox_iou(a, b) == 0.0


# ── Evidence dataclass invariants ───────────────────────────────────


def test_evidence_clamps_score() -> None:
    e1 = Evidence(field="x", value="v", page=0, evidence_score=1.5)
    assert e1.evidence_score == 1.0
    e2 = Evidence(field="x", value="v", page=0, evidence_score=-0.5)
    assert e2.evidence_score == 0.0


def test_evidence_clamps_bbox_to_unit() -> None:
    e = Evidence(field="x", value="v", page=0, bbox=(1.2, -0.1, 2.0, 0.5))
    assert e.bbox == (1.0, 0.0, 1.0, 0.5)


def test_evidence_negative_page_clamped_to_zero() -> None:
    e = Evidence(field="x", value="v", page=-3)
    assert e.page == 0


def test_evidence_to_dict() -> None:
    e = Evidence(
        field="vendor",
        value="Acme",
        page=0,
        bbox=(0.1, 0.1, 0.4, 0.2),
        text_span="Acme",
        evidence_score=0.9,
    )
    d = e.to_dict()
    assert d["field"] == "vendor"
    assert d["value"] == "Acme"
    assert d["bbox"] == [0.1, 0.1, 0.4, 0.2]
    assert d["text_span"] == "Acme"
    assert d["evidence_score"] == 0.9


# ── build_evidence_map ─────────────────────────────────────────────


def test_build_evidence_map_basic() -> None:
    payload = {
        "fields": {
            "vendor": {
                "value": "Acme",
                "evidence": {
                    "page": 0,
                    "bbox": [0.1, 0.05, 0.4, 0.07],
                    "text_span": "Acme Corp",
                    "score": 0.95,
                },
            },
            "total": {
                "value": 1500.0,
                "evidence": {
                    "page": 0,
                    "bbox": [0.1, 0.85, 0.4, 0.9],
                    "text_span": "Total: $1,500.00",
                    "score": 0.92,
                },
            },
        },
        "not_found": ["middle_name"],
    }
    m = build_evidence_map(payload)
    assert "vendor" in m
    assert "total" in m
    assert "middle_name" in m.not_found
    assert m.get("vendor").text_span == "Acme Corp"
    assert m.get("total").value == 1500.0


def test_build_evidence_map_drops_evidence_less_fields() -> None:
    payload = {
        "fields": {
            "vendor": {"value": "Acme"},
            "total": {
                "value": 100.0,
                "evidence": {"page": 0, "text_span": "100", "score": 0.8},
            },
        },
    }
    m = build_evidence_map(payload)
    assert "vendor" not in m
    assert "total" in m
    assert "vendor" in m.not_found


def test_build_evidence_map_drops_empty_text_span() -> None:
    payload = {
        "fields": {
            "vendor": {
                "value": "Acme",
                "evidence": {"page": 0, "text_span": "  ", "score": 0.9},
            },
        },
    }
    m = build_evidence_map(payload)
    assert "vendor" not in m
    assert "vendor" in m.not_found


def test_build_evidence_map_from_json_string() -> None:
    raw = json.dumps(
        {
            "fields": {
                "vendor": {
                    "value": "Acme",
                    "evidence": {"page": 0, "text_span": "Acme", "score": 0.9},
                },
            },
        }
    )
    m = build_evidence_map(raw)
    assert "vendor" in m


def test_build_evidence_map_handles_json_with_garbage() -> None:
    raw = 'Here is the result:\n{"fields": {"x": {"value": 1, "evidence": {"text_span": "1", "score": 0.9}}}}\nDone.'
    m = build_evidence_map(raw)
    assert "x" in m


def test_build_evidence_map_invalid_payload() -> None:
    assert len(build_evidence_map("not json at all")) == 0
    assert len(build_evidence_map("")) == 0
    assert len(build_evidence_map(None)) == 0  # type: ignore[arg-type]
    assert len(build_evidence_map([1, 2, 3])) == 0  # type: ignore[arg-type]


def test_build_evidence_map_with_string_bbox() -> None:
    payload = {
        "fields": {
            "x": {
                "value": 1,
                "evidence": {
                    "page": 0,
                    "bbox": "0.1, 0.2, 0.3, 0.4",
                    "text_span": "1",
                    "score": 0.9,
                },
            },
        },
    }
    m = build_evidence_map(payload)
    assert m.get("x").bbox == (0.1, 0.2, 0.3, 0.4)


def test_build_evidence_map_invalid_bbox() -> None:
    payload = {
        "fields": {
            "x": {
                "value": 1,
                "evidence": {
                    "page": 0,
                    "bbox": [0.1, 0.2, 0.05, 0.4],
                    "text_span": "1",
                    "score": 0.9,
                },
            },
        },
    }
    m = build_evidence_map(payload)
    # x1 < x0 → invalid → field is dropped
    assert "x" not in m


def test_build_evidence_map_with_region_id_alias() -> None:
    payload = {
        "fields": {
            "x": {
                "value": 1,
                "evidence": {"page": 0, "text_span": "1", "score": 0.9, "region_id": "r1"},
            },
        },
    }
    m = build_evidence_map(payload)
    assert m.get("x").source_region_id == "r1"


# ── filter_low_evidence ─────────────────────────────────────────────


def test_filter_low_evidence_drops_below_threshold() -> None:
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value=1, page=0, text_span="1", evidence_score=0.9),
            "b": Evidence(field="b", value=2, page=0, text_span="2", evidence_score=0.3),
        },
        not_found=[],
    )
    filtered = filter_low_evidence(m, min_evidence_score=0.5)
    assert "a" in filtered
    assert "b" not in filtered
    assert "b" in filtered.not_found


def test_filter_low_evidence_preserves_existing_not_found() -> None:
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value=1, page=0, text_span="1", evidence_score=0.9),
        },
        not_found=["x"],
    )
    filtered = filter_low_evidence(m, min_evidence_score=0.5)
    assert "x" in filtered.not_found
    assert "a" in filtered


def test_filter_low_evidence_does_not_mutate_input() -> None:
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value=1, page=0, text_span="1", evidence_score=0.9),
            "b": Evidence(field="b", value=2, page=0, text_span="2", evidence_score=0.3),
        },
    )
    filter_low_evidence(m, min_evidence_score=0.5)
    assert "b" in m  # original unchanged


# ── merge_with_not_found ───────────────────────────────────────────


def test_merge_with_not_found_basic() -> None:
    m = EvidenceMap(
        evidences={
            "vendor": Evidence(field="vendor", value="Acme", page=0, text_span="Acme"),
            "total": Evidence(field="total", value=100.0, page=0, text_span="100"),
        },
        not_found=["middle_name"],
    )
    out = merge_with_not_found(m)
    assert out["vendor"] == "Acme"
    assert out["total"] == 100.0
    assert out["_meta"]["not_found_fields"] == ["middle_name"]
    assert out["_meta"]["evidence_field_count"] == 2


def test_merge_with_not_found_without_meta() -> None:
    m = EvidenceMap(
        evidences={"a": Evidence(field="a", value=1, page=0, text_span="1")},
        not_found=[],
    )
    out = merge_with_not_found(m, include_meta=False)
    assert "_meta" not in out
    assert out["a"] == 1


# ── page_locality_correct ───────────────────────────────────────────


def test_page_locality_correct_basic() -> None:
    m = EvidenceMap(
        evidences={
            "a": Evidence(field="a", value=1, page=0, text_span="1"),
            "b": Evidence(field="b", value=2, page=2, text_span="2"),
        },
    )
    out = page_locality_correct(m, {"a": 0, "b": 1})
    assert out == {"a": True, "b": False}


def test_page_locality_correct_missing_evidence() -> None:
    m = EvidenceMap(evidences={})
    out = page_locality_correct(m, {"a": 0})
    assert out == {"a": False}


def test_page_locality_correct_no_expectation() -> None:
    m = EvidenceMap(
        evidences={"a": Evidence(field="a", value=1, page=5, text_span="1")},
    )
    out = page_locality_correct(m, {})
    assert out == {}


# ── save / load round-trip ──────────────────────────────────────────


def test_save_load_evidence_map_round_trip(tmp_path: Path) -> None:
    m = EvidenceMap(
        evidences={
            "vendor": Evidence(
                field="vendor",
                value="Acme",
                page=0,
                bbox=(0.1, 0.1, 0.4, 0.2),
                text_span="Acme",
                evidence_score=0.9,
            ),
        },
        not_found=["middle_name"],
    )
    target = tmp_path / "evidence.json"
    save_evidence_map(m, target)
    loaded = load_evidence_map(target)
    assert "vendor" in loaded
    assert loaded.get("vendor").value == "Acme"
    assert loaded.get("vendor").bbox == (0.1, 0.1, 0.4, 0.2)
    assert loaded.get("vendor").text_span == "Acme"
    assert loaded.not_found == ["middle_name"]


def test_save_load_evidence_map_no_bbox(tmp_path: Path) -> None:
    m = EvidenceMap(
        evidences={"a": Evidence(field="a", value=1, page=0, text_span="1")},
    )
    target = tmp_path / "evidence.json"
    save_evidence_map(m, target)
    loaded = load_evidence_map(target)
    assert loaded.get("a").bbox is None
