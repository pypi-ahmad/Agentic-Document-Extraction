"""Deterministic quality gates and reconciliation helpers for V2 page drafts."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw

from app.services.parsing.contracts import BoundingBox
from app.services.parsing.v2_contracts import GroundedChunk, VerificationStatus

OVERLAP_THRESHOLD = 0.50
UNCOVERED_INK_THRESHOLD = 0.12
_HIDDEN_FORMATTING = "\u00ad\u200b\u200c\u200d\ufeff"
_CRITICAL_TOKEN_PATTERNS = (
    re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.IGNORECASE),
    re.compile(r"(?:https?://|www\.)[^\s<>]+", re.IGNORECASE),
    re.compile(r"(?<!\w)(?:\+?\d[\d().\s-]{6,}\d)(?!\w)"),
    re.compile(r"(?<!\w)[A-Z]{1,12}(?:[#\d][A-Z0-9#-]*)(?!\w)", re.IGNORECASE),
    re.compile(r"(?m)^\s*\d{1,3}[.)](?=\s)"),
)


@dataclass(frozen=True)
class PageQualityAssessment:
    flagged: bool
    reasons: tuple[str, ...]
    uncovered_ink_ratio: float


def normalize_extracted_text(value: str) -> str:
    value = value.translate({ord(character): None for character in _HIDDEN_FORMATTING})
    value = re.sub(r"(?<=[A-Za-z])-[ \t]*\r?\n[ \t]*(?=[a-z])", "", value)
    value = re.sub(r"(?<=\d)-[ \t]*\r?\n[ \t]*(?=\d)", "-", value)
    value = re.sub(r"[ \t]*\r?\n[ \t]*", " ", value)
    return " ".join(value.split())


def extract_critical_tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for pattern in _CRITICAL_TOKEN_PATTERNS:
        for match in pattern.finditer(value):
            token = " ".join(match.group(0).split()).rstrip(".,;:").casefold()
            if token:
                tokens.add(token)
    return tokens


def requires_precision_verification(chunk_type: str, text: str, box: BoundingBox) -> bool:
    if extract_critical_tokens(text):
        return True
    normalized = normalize_extracted_text(text)
    return chunk_type in {"form_field", "checkbox"} and not normalized


def clean_repeated_labels(value: str, previous_heading: str | None = None) -> str:
    cleaned = value.translate({ord(character): None for character in _HIDDEN_FORMATTING})
    cleaned = re.sub(r"<strong>(.*?)</strong>", r"**\1**", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"</?p>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    if previous_heading:
        heading = previous_heading.strip()
        if cleaned.strip().rstrip(":").casefold() == heading.rstrip(":").casefold():
            return ""
        prefix = re.match(r"^.{1,64}?:?(?=\r?\n|\s{2,})", cleaned)
        if (
            prefix
            and prefix.group(0).strip().rstrip(":").casefold() == heading.rstrip(":").casefold()
        ):
            cleaned = cleaned[prefix.end() :].lstrip()
        elif cleaned.casefold().startswith(heading.casefold() + "\n"):
            cleaned = cleaned[len(heading) :].lstrip()
    repeated = re.compile(
        r"^([A-Za-z][A-Za-z0-9 /&]{1,63})(\s+[\-\u2013\u2014]\s+)\1(\s+[\-\u2013\u2014]\s+)",
        re.IGNORECASE,
    )
    return repeated.sub(lambda match: match.group(1) + match.group(3), cleaned, count=1)


def normalized_key(value: str) -> str:
    return normalize_extracted_text(value).casefold()


def overlap_over_smaller_area(first: BoundingBox, second: BoundingBox) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = width * height
    first_area = (first.right - first.left) * (first.bottom - first.top)
    second_area = (second.right - second.left) * (second.bottom - second.top)
    smaller = min(first_area, second_area)
    return intersection / smaller if smaller else 0.0


def assess_page_quality(
    chunks: list[tuple[GroundedChunk, BoundingBox]], image_png: bytes
) -> PageQualityAssessment:
    reasons: list[str] = []
    top_level = [(chunk, box) for chunk, box in chunks if chunk.parent_id is None]
    if any(
        overlap_over_smaller_area(first_box, second_box) >= OVERLAP_THRESHOLD
        for index, (_, first_box) in enumerate(top_level)
        for _, second_box in top_level[index + 1 :]
    ):
        reasons.append("overlapping_siblings")
    keys = [normalized_key(chunk.text) for chunk, _ in chunks if chunk.text.strip()]
    if len(keys) != len(set(keys)):
        reasons.append("duplicate_text")
    risky_types = {"table", "table_cell", "form_field", "checkbox"}
    if any(chunk.type in risky_types for chunk, _ in chunks):
        reasons.append("complex_layout")
    uncovered = _uncovered_ink_ratio(image_png, [box for _, box in chunks])
    if uncovered > UNCOVERED_INK_THRESHOLD:
        reasons.append("uncovered_ink")
    return PageQualityAssessment(bool(reasons), tuple(reasons), uncovered)


def _uncovered_ink_ratio(image_png: bytes, boxes: list[BoundingBox]) -> float:
    image = Image.open(BytesIO(image_png)).convert("L")
    width, height = image.size
    ink = image.point([255 if pixel < 220 else 0 for pixel in range(256)])
    inner = Image.new("L", image.size, 0)
    ImageDraw.Draw(inner).rectangle(
        (int(width * 0.02), int(height * 0.02), int(width * 0.98), int(height * 0.98)), fill=255
    )
    ink = ImageChops.multiply(ink, inner)
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    for box in boxes:
        draw.rectangle(
            (
                int(max(0, box.left - 0.01) * width),
                int(max(0, box.top - 0.01) * height),
                int(min(1, box.right + 0.01) * width),
                int(min(1, box.bottom + 0.01) * height),
            ),
            fill=255,
        )
    total = sum(ink.histogram()[1:])
    uncovered = sum(ImageChops.subtract(ink, mask).histogram()[1:])
    return uncovered / total if total else 0.0


def suppress_duplicate_chunks(
    chunks: list[tuple[GroundedChunk, BoundingBox]],
) -> list[tuple[GroundedChunk, BoundingBox]]:
    rank = {
        VerificationStatus.VERIFIED: 2,
        VerificationStatus.CANDIDATE: 1,
        VerificationStatus.UNRESOLVED: 0,
    }
    type_rank = {
        "table": 6,
        "table_cell": 6,
        "checkbox": 6,
        "form_field": 6,
        "list": 5,
        "title": 4,
        "heading": 4,
        "header": 3,
        "footer": 3,
        "text": 2,
        "figure": 1,
        "chart": 1,
    }

    def token_count(chunk: GroundedChunk) -> int:
        return len(re.findall(r"\w+", normalized_key(chunk.text)))

    def relation(first: GroundedChunk, second: GroundedChunk) -> str | None:
        first_key = normalized_key(first.text)
        second_key = normalized_key(second.text)
        if not first_key or not second_key:
            return None
        length_ratio = min(len(first_key), len(second_key)) / max(len(first_key), len(second_key))
        if (
            length_ratio >= 0.8
            and SequenceMatcher(None, first_key, second_key, autojunk=False).ratio() >= 0.95
        ):
            return "near"
        first_tokens = re.findall(r"\w+", first_key)
        second_tokens = re.findall(r"\w+", second_key)
        shorter, longer = (
            (first_tokens, second_tokens)
            if len(first_tokens) <= len(second_tokens)
            else (second_tokens, first_tokens)
        )
        if len(shorter) < 5 or {first.type, second.type} & {"figure", "chart"}:
            return None
        recall = sum((Counter(shorter) & Counter(longer)).values()) / len(shorter)
        return "contained" if recall >= 0.8 else None

    def duplicate_rank(chunk: GroundedChunk) -> tuple[int, int, int, int, int]:
        exact_grounding = int(
            any(grounding.method.value == "text_layer_exact" for grounding in chunk.grounding)
        )
        return (
            rank[chunk.verification_status],
            exact_grounding,
            type_rank[chunk.type],
            len(normalized_key(chunk.text)),
            -chunk.order,
        )

    kept: list[tuple[GroundedChunk, BoundingBox]] = []
    for chunk, box in chunks:
        conflicts: list[tuple[int, str]] = []
        for index, (other, other_box) in enumerate(kept):
            if overlap_over_smaller_area(box, other_box) < OVERLAP_THRESHOLD:
                continue
            duplicate_relation = relation(chunk, other)
            if duplicate_relation is None:
                continue
            if duplicate_relation == "contained":
                longer, shorter = sorted((chunk, other), key=token_count, reverse=True)
                if rank[longer.verification_status] < rank[shorter.verification_status]:
                    continue
            conflicts.append((index, duplicate_relation))
        if not conflicts:
            kept.append((chunk, box))
            continue
        winner = (chunk, box)
        for index, duplicate_relation in conflicts:
            other = kept[index]
            if duplicate_relation == "contained":
                winner = max((winner, other), key=lambda item: token_count(item[0]))
            else:
                winner = max((winner, other), key=lambda item: duplicate_rank(item[0]))
        for index, _ in reversed(conflicts):
            kept.pop(index)
        kept.append(winner)
    return sorted(kept, key=lambda item: item[0].order)


__all__ = [
    "PageQualityAssessment",
    "assess_page_quality",
    "clean_repeated_labels",
    "extract_critical_tokens",
    "normalize_extracted_text",
    "overlap_over_smaller_area",
    "requires_precision_verification",
    "suppress_duplicate_chunks",
]
