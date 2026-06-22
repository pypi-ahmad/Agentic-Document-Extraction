"""Evidence-grounded extraction (v0.5.0).

Every field the LLM extracts MUST cite evidence: which page, which
bbox, which text span in the document backs the value. This
prevents the LLM from hallucinating plausible-but-wrong values
that the v0.4.0 self-reported confidence would happily let
through.

Public API
----------

* :class:`Evidence` — a single field's evidence record.
* :class:`EvidenceMap` — full evidence for one extraction.
* :func:`build_evidence_map` — parse the LLM JSON output into an
  :class:`EvidenceMap`, rejecting fields without evidence.
* :func:`filter_low_evidence` — drop fields whose
  ``evidence_score < threshold``; emit a ``not_found`` record
  for each dropped field.
* :func:`merge_with_not_found` — compute the final extraction
  payload (values + ``_meta.not_found_fields``).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────

# Bbox values are normalized to [0, 1] across the page.
BBOX_PATTERN = re.compile(
    r"^\s*\[?\s*"
    r"(?P<x0>\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y0>\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<x1>\d+(?:\.\d+)?)\s*,\s*"
    r"(?P<y1>\d+(?:\.\d+)?)\s*"
    r"\]?\s*$"
)


def _parse_bbox(value: Any) -> tuple[float, float, float, float] | None:
    """Parse a bbox from a JSON value: list of 4 floats, or string ``"x0,y0,x1,y1"``."""

    if value is None:
        return None
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            x0, y0, x1, y1 = (float(v) for v in value)
        except (TypeError, ValueError):
            return None
        return _validate_bbox(x0, y0, x1, y1)
    if isinstance(value, str):
        match = BBOX_PATTERN.match(value)
        if not match:
            return None
        x0, y0, x1, y1 = (float(match.group(k)) for k in ("x0", "y0", "x1", "y1"))
        return _validate_bbox(x0, y0, x1, y1)
    return None


def _validate_bbox(
    x0: float, y0: float, x1: float, y1: float
) -> tuple[float, float, float, float] | None:
    """Return a normalized bbox, or None if invalid."""

    coords = (x0, y0, x1, y1)
    if any(c < 0 or c > 1.5 for c in coords):  # tolerate 0..1.5 for sloppy sources
        return None
    # Reject degenerate boxes
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _clamp_bbox_to_unit(
    bbox: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    """Clamp bbox coordinates to [0, 1]."""

    return tuple(max(0.0, min(1.0, c)) for c in bbox)  # type: ignore[return-value]


# ── Evidence data classes ────────────────────────────────────────────


@dataclass(frozen=True)
class Evidence:
    """Evidence for a single extracted field.

    Attributes:
        field: Schema field name.
        value: Extracted value (string, number, or structured).
        page: 0-indexed page number.
        bbox: Normalized 0..1 bbox on the page, or None.
        text_span: Verbatim text in the document that backs the value.
        source_region_id: Optional layout region id (from
            :class:`LayoutResult`).
        evidence_score: 0..1 — the LLM's self-assessed confidence
            in the evidence (NOT the value's correctness).
    """

    field: str
    value: Any
    page: int
    bbox: tuple[float, float, float, float] | None = None
    text_span: str = ""
    source_region_id: str | None = None
    evidence_score: float = 0.0

    def __post_init__(self) -> None:
        # Clamp evidence_score to [0, 1]
        if self.evidence_score < 0.0:
            object.__setattr__(self, "evidence_score", 0.0)
        elif self.evidence_score > 1.0:
            object.__setattr__(self, "evidence_score", 1.0)
        if self.bbox is not None:
            object.__setattr__(self, "bbox", _clamp_bbox_to_unit(self.bbox))
        if self.page < 0:
            object.__setattr__(self, "page", 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "page": self.page,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "text_span": self.text_span,
            "source_region_id": self.source_region_id,
            "evidence_score": self.evidence_score,
        }


@dataclass
class EvidenceMap:
    """Full evidence map for one extraction."""

    evidences: dict[str, Evidence] = field(default_factory=dict)
    not_found: list[str] = field(default_factory=list)
    raw_llm_payload: dict[str, Any] | None = None

    def get(self, field: str) -> Evidence | None:
        return self.evidences.get(field)

    def __contains__(self, field: str) -> bool:
        return field in self.evidences

    def __len__(self) -> int:
        return len(self.evidences)

    def fields(self) -> list[str]:
        return list(self.evidences.keys())

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidences": {k: v.to_dict() for k, v in self.evidences.items()},
            "not_found": list(self.not_found),
        }


# ── Building an evidence map from LLM output ────────────────────────


def build_evidence_map(
    llm_payload: dict[str, Any] | str,
    *,
    default_page: int = 0,
) -> EvidenceMap:
    """Parse the LLM's evidence-aware JSON output.

    The LLM is expected to emit:

    .. code-block:: json

        {
          "fields": {
            "vendor_name": {
              "value": "Acme",
              "evidence": {
                "page": 0,
                "bbox": [0.1, 0.05, 0.4, 0.07],
                "text_span": "Acme Corp",
                "score": 0.95
              }
            }
          },
          "not_found": ["middle_name"]
        }

    Fields without an evidence block, or with an empty text_span,
    are rejected (the LLM is asked to mark them ``not_found``).
    The returned :class:`EvidenceMap` contains only the accepted
    fields plus a ``not_found`` list.
    """

    payload = _coerce_payload(llm_payload)
    if not isinstance(payload, dict):
        return EvidenceMap(raw_llm_payload=None)

    fields_obj = payload.get("fields")
    if not isinstance(fields_obj, dict):
        fields_obj = {}

    not_found_raw = payload.get("not_found", [])
    not_found: list[str] = []
    if isinstance(not_found_raw, list):
        not_found = [str(x) for x in not_found_raw if isinstance(x, (str, int, float))]

    evidences: dict[str, Evidence] = {}
    for field_name, field_def in fields_obj.items():
        if not isinstance(field_def, dict):
            continue
        value = field_def.get("value")
        evidence_block = field_def.get("evidence")
        if not isinstance(evidence_block, dict):
            # LLM did not cite evidence → drop the field.
            if field_name not in not_found:
                not_found.append(field_name)
            continue
        text_span = str(evidence_block.get("text_span", "")).strip()
        if not text_span:
            # Empty text span → no real evidence. Reject.
            if field_name not in not_found:
                not_found.append(field_name)
            continue
        page_raw = evidence_block.get("page", default_page)
        try:
            page = int(page_raw)
        except (TypeError, ValueError):
            page = default_page
        bbox_raw = evidence_block.get("bbox")
        bbox: tuple[float, float, float, float] | None = None
        if bbox_raw is not None:
            bbox = _parse_bbox(bbox_raw)
            if bbox is None:
                # Bbox was provided but invalid (e.g. degenerate, out of
                # range). Reject the field — bad bbox is worse than no bbox.
                if field_name not in not_found:
                    not_found.append(field_name)
                continue
        score_raw = evidence_block.get("score", evidence_block.get("evidence_score", 0.0))
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = 0.0
        region_id = evidence_block.get("region_id") or evidence_block.get("source_region_id")
        evidences[field_name] = Evidence(
            field=field_name,
            value=value,
            page=page,
            bbox=bbox,
            text_span=text_span,
            source_region_id=str(region_id) if region_id is not None else None,
            evidence_score=score,
        )

    return EvidenceMap(
        evidences=evidences,
        not_found=not_found,
        raw_llm_payload=payload,
    )


def _coerce_payload(llm_payload: dict[str, Any] | str) -> dict[str, Any] | None:
    """Coerce a JSON string or dict to a dict payload."""

    if isinstance(llm_payload, dict):
        return llm_payload
    if not isinstance(llm_payload, str):
        return None
    text = llm_payload.strip()
    if not text:
        return None
    # Try to extract the largest JSON object in the response
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


# ── Filtering low-evidence fields ───────────────────────────────────


def filter_low_evidence(
    evidence_map: EvidenceMap,
    *,
    min_evidence_score: float = 0.5,
) -> EvidenceMap:
    """Drop fields whose ``evidence_score < min_evidence_score``.

    Dropped fields are added to ``not_found`` so the caller can
    surface them in the response. The input map is not mutated.
    """

    kept: dict[str, Evidence] = {}
    dropped: list[str] = []
    for fname, ev in evidence_map.evidences.items():
        if ev.evidence_score < min_evidence_score:
            dropped.append(fname)
        else:
            kept[fname] = ev
    new_not_found = list(evidence_map.not_found)
    for f in dropped:
        if f not in new_not_found:
            new_not_found.append(f)
    return EvidenceMap(
        evidences=kept,
        not_found=new_not_found,
        raw_llm_payload=evidence_map.raw_llm_payload,
    )


# ── Merging into the final extraction payload ───────────────────────


def merge_with_not_found(
    evidence_map: EvidenceMap,
    *,
    include_meta: bool = True,
) -> dict[str, Any]:
    """Build the final extraction payload: ``{field: value, ..., _meta: {...}}``.

    The ``_meta`` block lists fields the LLM could not ground and
    the evidence map id (so the UI can drill down). Set
    ``include_meta=False`` to drop the meta block.
    """

    out: dict[str, Any] = {}
    for fname, ev in evidence_map.evidences.items():
        out[fname] = ev.value
    if include_meta:
        out["_meta"] = {
            "not_found_fields": list(evidence_map.not_found),
            "evidence_field_count": len(evidence_map.evidences),
        }
    return out


# ── IoU between two bboxes (used by metrics + verifier) ─────────────


def bbox_iou(
    a: tuple[float, float, float, float] | None,
    b: tuple[float, float, float, float] | None,
) -> float:
    """Compute IoU between two bboxes in [0, 1]^2.

    Returns 0.0 if either bbox is None or degenerate.
    """

    if a is None or b is None:
        return 0.0
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    if ax1 <= ax0 or ay1 <= ay0 or bx1 <= bx0 or by1 <= by0:
        return 0.0
    inter_x0 = max(ax0, bx0)
    inter_y0 = max(ay0, by0)
    inter_x1 = min(ax1, bx1)
    inter_y1 = min(ay1, by1)
    if inter_x1 <= inter_x0 or inter_y1 <= inter_y0:
        return 0.0
    inter = (inter_x1 - inter_x0) * (inter_y1 - inter_y0)
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return float(inter / union)


# ── Page-locality accuracy helper ───────────────────────────────────


def page_locality_correct(
    evidence_map: EvidenceMap,
    expected_pages: dict[str, int],
) -> dict[str, bool]:
    """For each field, return whether ``evidence.page == expected_pages[field]``.

    Fields missing from ``expected_pages`` are reported as ``True``
    (no expectation). Fields whose evidence is missing are reported
    as ``False``.
    """

    out: dict[str, bool] = {}
    for fname, expected_page in expected_pages.items():
        ev = evidence_map.evidences.get(fname)
        if ev is None:
            out[fname] = False
        else:
            out[fname] = ev.page == expected_page
    return out


# ── File-system persistence helper (optional) ───────────────────────


def save_evidence_map(evidence_map: EvidenceMap, path: Path) -> None:
    """Persist an evidence map as JSON. The path's parent must exist."""

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "evidences": {k: v.to_dict() for k, v in evidence_map.evidences.items()},
        "not_found": list(evidence_map.not_found),
    }
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def load_evidence_map(path: Path) -> EvidenceMap:
    """Load a previously-saved evidence map from disk."""

    payload = json.loads(path.read_text())
    evidences: dict[str, Evidence] = {}
    for fname, ev in payload.get("evidences", {}).items():
        bbox = ev.get("bbox")
        if bbox is not None:
            bbox = tuple(float(x) for x in bbox)  # type: ignore[assignment]
        evidences[fname] = Evidence(
            field=fname,
            value=ev.get("value"),
            page=int(ev.get("page", 0)),
            bbox=bbox,  # type: ignore[arg-type]
            text_span=ev.get("text_span", ""),
            source_region_id=ev.get("source_region_id"),
            evidence_score=float(ev.get("evidence_score", 0.0)),
        )
    return EvidenceMap(
        evidences=evidences,
        not_found=list(payload.get("not_found", [])),
    )
