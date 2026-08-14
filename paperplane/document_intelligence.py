"""Document-level relations inferred only from selected, grounded pages."""

from __future__ import annotations

from collections import Counter
from itertools import pairwise
from typing import Any

from paperplane.contracts import ParseResponse, StructureNode


def _normalized(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def infer_document_relations(response: ParseResponse) -> list[dict[str, Any]]:
    """Infer conservative section, repeated-label, and table-continuation relations."""

    pages = response.structure.children
    relations: list[dict[str, Any]] = []
    marginalia = Counter(
        _normalized(block.text)
        for page in pages
        for block in page.children
        if block.type == "marginalia" and _normalized(block.text)
    )
    for page in pages:
        for block in page.children:
            if block.semantic_role in {"title", "heading"}:
                relations.append(
                    {
                        "type": "section_start",
                        "block_id": block.id,
                        "page": page.page,
                        "title": (block.text or "").splitlines()[0],
                    }
                )
            if block.type == "marginalia" and marginalia[_normalized(block.text)] > 1:
                relations.append(
                    {"type": "repeated_marginalia", "block_id": block.id, "page": page.page}
                )

    for previous, current in pairwise(pages):
        previous_tables = [block for block in previous.children if block.type == "table"]
        current_tables = [block for block in current.children if block.type == "table"]
        if not previous_tables or not current_tables:
            continue
        left, right = previous_tables[-1], current_tables[0]
        left_columns = max((cell.col or 0 for cell in left.children), default=-1) + 1
        right_columns = max((cell.col or 0 for cell in right.children), default=-1) + 1
        if left_columns and left_columns == right_columns:
            relations.append(
                {
                    "type": "continued_table",
                    "from_block_id": left.id,
                    "to_block_id": right.id,
                    "from_page": previous.page,
                    "to_page": current.page,
                    "column_count": left_columns,
                }
            )
    if response.metadata.page_range and response.metadata.source_page_count:
        start, end = response.metadata.page_range
        if start > 1 or end < response.metadata.source_page_count:
            relations.append(
                {
                    "type": "selection_boundary",
                    "page_range": [start, end],
                    "warning": "Pages outside the selected range were not inspected.",
                }
            )
    return relations


def blocks_in_reading_order(response: ParseResponse) -> list[StructureNode]:
    return [block for page in response.structure.children for block in page.children]


__all__ = ["blocks_in_reading_order", "infer_document_relations"]
