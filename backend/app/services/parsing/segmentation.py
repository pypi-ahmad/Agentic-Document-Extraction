"""Conservative, evidence-grounded segmentation of mixed document files."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Literal

from pydantic import BaseModel, Field

from app.services.parsing.contracts import ContextChunk
from app.services.parsing.domain_extraction import DocumentProfile, classify_profile

SegmentProfile = DocumentProfile | Literal["unknown"]

_IDENTIFIERS: dict[str, re.Pattern[str]] = {
    "invoice_number": re.compile(
        r"\binvoice\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,})",
        re.I,
    ),
    "order_id": re.compile(
        r"\b(?:order|purchase\s+order|po)\s*(?:id|number|no\.?|#)?\s*[:#-]\s*([A-Z0-9][A-Z0-9._/-]{1,})",
        re.I,
    ),
    "claim_number": re.compile(
        r"\bclaim\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,})",
        re.I,
    ),
    "policy_number": re.compile(
        r"\bpolicy\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{1,})",
        re.I,
    ),
    "medical_record_number": re.compile(
        r"\b(?:medical\s+record(?:\s+number)?|mrn)\s*[:#-]\s*([A-Z0-9][A-Z0-9._/-]{1,})",
        re.I,
    ),
    "document_id": re.compile(
        r"\bdocument\s*(?:id|number|no\.?)\s*[:#-]\s*([A-Z0-9][A-Z0-9._/-]{1,})",
        re.I,
    ),
}


class IdentifierEvidence(BaseModel):
    kind: str
    value: str
    normalized_value: str
    page: int = Field(ge=1)
    region_id: str
    confidence: float = Field(default=0.95, ge=0, le=1)


class DetectedSubDocument(BaseModel):
    ordinal: int = Field(ge=1)
    start_page: int = Field(ge=1)
    end_page: int = Field(ge=1)
    profile: SegmentProfile
    confidence: float = Field(ge=0, le=1)
    identifiers: list[IdentifierEvidence] = Field(default_factory=list)
    boundary_confidence: float = Field(ge=0, le=1)
    boundary_reasons: list[str] = Field(default_factory=list)
    complete: bool = True
    missing_pages: list[int] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class _PageDescriptor(BaseModel):
    page: int
    profile: SegmentProfile
    profile_confidence: float
    identifiers: list[IdentifierEvidence]


def segment_document(
    chunks: list[ContextChunk], *, expected_pages: list[int]
) -> list[DetectedSubDocument]:
    if not expected_pages:
        return []
    by_page: dict[int, list[ContextChunk]] = defaultdict(list)
    for chunk in chunks:
        by_page[chunk.page].append(chunk)
    descriptors = [_describe_page(page, by_page.get(page, [])) for page in expected_pages]
    boundaries: list[tuple[int, float, list[str]]] = []
    for index in range(1, len(descriptors)):
        confidence, reasons = _boundary(descriptors[index - 1], descriptors[index])
        if confidence >= 0.8:
            boundaries.append((index, confidence, reasons))

    starts = [0, *(item[0] for item in boundaries)]
    ends = [*(item[0] for item in boundaries), len(descriptors)]
    results: list[DetectedSubDocument] = []
    for ordinal, (start, end) in enumerate(zip(starts, ends, strict=True), start=1):
        group = descriptors[start:end]
        page_chunks = [chunk for page in group for chunk in by_page.get(page.page, [])]
        profile, confidence = classify_profile(page_chunks)
        if not any(chunk.text.strip() for chunk in page_chunks):
            profile, confidence = "unknown", 0.0
        missing = [page.page for page in group if not by_page.get(page.page)]
        boundary_confidence, boundary_reasons = (
            (1.0, ["start_of_file"])
            if start == 0
            else (boundaries[ordinal - 2][1], boundaries[ordinal - 2][2])
        )
        unique_identifiers: dict[tuple[str, str], IdentifierEvidence] = {}
        for page in group:
            for identifier in page.identifiers:
                unique_identifiers.setdefault(
                    (identifier.kind, identifier.normalized_value), identifier
                )
        results.append(
            DetectedSubDocument(
                ordinal=ordinal,
                start_page=group[0].page,
                end_page=group[-1].page,
                profile=profile,
                confidence=confidence,
                identifiers=list(unique_identifiers.values()),
                boundary_confidence=boundary_confidence,
                boundary_reasons=boundary_reasons,
                complete=not missing,
                missing_pages=missing,
                warnings=["missing_pages"] if missing else [],
            )
        )
    return results


def _describe_page(page: int, chunks: list[ContextChunk]) -> _PageDescriptor:
    if chunks:
        profile, confidence = classify_profile(chunks)
    else:
        profile, confidence = "unknown", 0.0
    identifiers: list[IdentifierEvidence] = []
    for chunk in chunks:
        text = " ".join(chunk.text.split())
        for kind, pattern in _IDENTIFIERS.items():
            for match in pattern.finditer(text):
                value = match.group(1).strip().rstrip(".,;:")
                identifiers.append(
                    IdentifierEvidence(
                        kind=kind,
                        value=value,
                        normalized_value=value.upper(),
                        page=page,
                        region_id=chunk.id,
                    )
                )
    return _PageDescriptor(
        page=page,
        profile=profile,
        profile_confidence=confidence,
        identifiers=identifiers,
    )


def _boundary(previous: _PageDescriptor, current: _PageDescriptor) -> tuple[float, list[str]]:
    previous_ids = {item.kind: item.normalized_value for item in previous.identifiers}
    current_ids = {item.kind: item.normalized_value for item in current.identifiers}
    changed = sorted(
        kind
        for kind in previous_ids.keys() & current_ids.keys()
        if previous_ids[kind] != current_ids[kind]
    )
    if changed:
        return 0.98, [f"identifier_changed:{kind}" for kind in changed]
    if (
        previous.profile not in {"general_scanned", "unknown"}
        and current.profile not in {"general_scanned", "unknown"}
        and previous.profile != current.profile
        and previous.profile_confidence >= 0.65
        and current.profile_confidence >= 0.65
    ):
        return 0.88, [f"profile_changed:{previous.profile}:{current.profile}"]
    return 0.0, []
