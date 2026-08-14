"""Cited, deterministic organization workflows built on grounded Parse output."""

from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from paperplane.contracts import CodepointRange, ParseResponse, StructureNode


class ClassDefinition(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""


class ClassifiedPage(BaseModel):
    page: int
    label: str
    reason: str
    ranges: list[CodepointRange]


class ClassifyResponse(BaseModel):
    pages: list[ClassifiedPage]
    warnings: list[str] = Field(default_factory=list)


class SectionResult(BaseModel):
    title: str
    level: int = 1
    section_number: int
    start_reference: str
    page: int
    ranges: list[CodepointRange]


class SectionResponse(BaseModel):
    sections: list[SectionResult]
    markdown: str
    warnings: list[str] = Field(default_factory=list)


class SplitResult(BaseModel):
    label: str
    pages: list[int]
    markdown: str
    ranges: list[CodepointRange]


class SplitResponse(BaseModel):
    documents: list[SplitResult]
    warnings: list[str] = Field(default_factory=list)


def _page_ranges(page: StructureNode) -> list[CodepointRange]:
    ranges = [item for block in page.children for item in block.ranges]
    return (
        [
            CodepointRange(
                start=min(item.start for item in ranges), end=max(item.end for item in ranges)
            )
        ]
        if ranges
        else []
    )


def _class_for_text(text: str, classes: list[ClassDefinition]) -> tuple[str, str]:
    normalized = text.casefold()
    for candidate in classes:
        terms = set(
            re.findall(r"[a-z0-9]+", f"{candidate.name} {candidate.description}".casefold())
        )
        hits = sorted(term for term in terms if len(term) > 3 and term in normalized)
        if hits:
            return candidate.name, f"Matched source term: {hits[0]}"
    return classes[0].name, "No deterministic keyword match; returned the first allowed class"


def classify_document(response: ParseResponse, classes: list[ClassDefinition]) -> ClassifyResponse:
    if not classes:
        raise ValueError("At least one class is required")
    pages: list[ClassifiedPage] = []
    warnings: list[str] = []
    for page in response.structure.children:
        ranges = _page_ranges(page)
        text = " ".join(response.markdown[item.start : item.end] for item in ranges)
        label, reason = _class_for_text(text, classes)
        if reason.startswith("No deterministic"):
            warnings.append(f"Page {page.page}: classification is a deterministic partial")
        pages.append(
            ClassifiedPage(
                page=page.page or len(pages) + 1, label=label, reason=reason, ranges=ranges
            )
        )
    return ClassifyResponse(pages=pages, warnings=warnings)


def section_document(response: ParseResponse) -> SectionResponse:
    sections: list[SectionResult] = []
    warnings: list[str] = []
    for page in response.structure.children:
        candidates = [block for block in page.children if block.ranges]
        if not candidates:
            continue
        first = candidates[0]
        if first.semantic_role not in {"title", "heading"}:
            warnings.append(
                f"Page {page.page}: no explicit heading; first grounded block used as a partial"
            )
        title = (first.text or "Untitled section").splitlines()[0].strip() or "Untitled section"
        sections.append(
            SectionResult(
                title=title[:160],
                section_number=len(sections) + 1,
                start_reference=first.id,
                page=page.page or len(sections) + 1,
                ranges=first.ranges,
            )
        )
    return SectionResponse(sections=sections, markdown=response.markdown, warnings=warnings)


def split_document(response: ParseResponse, classes: list[ClassDefinition]) -> SplitResponse:
    classified = classify_document(response, classes)
    grouped: defaultdict[str, list[ClassifiedPage]] = defaultdict(list)
    for page in classified.pages:
        grouped[page.label].append(page)
    documents: list[SplitResult] = []
    for label, pages in grouped.items():
        ranges = [item for page in pages for item in page.ranges]
        markdown = "\n\n<!-- PAGE BREAK -->\n\n".join(
            "".join(response.markdown[item.start : item.end] for item in page.ranges)
            for page in pages
        )
        documents.append(
            SplitResult(
                label=label,
                pages=[page.page for page in pages],
                markdown=markdown,
                ranges=ranges,
            )
        )
    return SplitResponse(documents=documents, warnings=classified.warnings)


__all__ = [
    "ClassDefinition",
    "classify_document",
    "section_document",
    "split_document",
]
