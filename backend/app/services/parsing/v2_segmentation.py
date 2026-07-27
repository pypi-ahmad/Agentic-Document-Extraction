"""Evidence-grounded mixed-document splitting for V2 chunks."""

from __future__ import annotations

import re
from collections import defaultdict

from app.services.parsing.v2_contracts import DocumentSplit, GroundedChunk

_IDENTIFIERS = [
    (
        "invoice",
        re.compile(r"\binvoice\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]+)", re.I),
    ),
    (
        "order",
        re.compile(
            r"\b(?:order|purchase\s+order|po)\s*(?:id|number|no\.?|#)?\s*[:#-]\s*([A-Z0-9][A-Z0-9._/-]+)",
            re.I,
        ),
    ),
    ("claim", re.compile(r"\bclaim\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]+)", re.I)),
    (
        "policy",
        re.compile(r"\bpolicy\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]+)", re.I),
    ),
]


def build_document_splits(
    chunks: list[GroundedChunk], *, page_count: int, enabled: bool
) -> list[DocumentSplit]:
    by_page: dict[int, list[GroundedChunk]] = defaultdict(list)
    for chunk in chunks:
        by_page[chunk.page].append(chunk)
    descriptors: list[tuple[str, str | None]] = []
    for page in range(1, page_count + 1):
        combined = "\n".join(chunk.text for chunk in by_page.get(page, []))
        match_value: tuple[str, str | None] = ("full", None)
        if enabled:
            for classification, pattern in _IDENTIFIERS:
                match = pattern.search(combined)
                if match:
                    match_value = (classification, match.group(1).upper())
                    break
        descriptors.append(match_value)

    groups: list[tuple[int, int, str, str | None, list[str]]] = []
    start = 1
    current_class, current_id = descriptors[0]
    reasons = ["start_of_file"]
    for page in range(2, page_count + 1):
        classification, identifier = descriptors[page - 1]
        if enabled and current_id and identifier and identifier != current_id:
            groups.append((start, page - 1, current_class, current_id, reasons))
            start = page
            current_class, current_id = classification, identifier
            reasons = ["identifier_changed"]
        elif current_id is None and identifier is not None:
            current_class, current_id = classification, identifier
    groups.append((start, page_count, current_class, current_id, reasons))

    return [
        DocumentSplit(
            id=f"split-{index:04d}",
            classification=classification,
            identifier=identifier or "full",
            pages=list(range(start_page, end_page + 1)),
            item_ids=[chunk.id for chunk in chunks if start_page <= chunk.page <= end_page],
            boundary_reasons=boundary_reasons,
        )
        for index, (
            start_page,
            end_page,
            classification,
            identifier,
            boundary_reasons,
        ) in enumerate(groups, start=1)
    ]
