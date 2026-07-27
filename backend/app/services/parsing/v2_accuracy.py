"""Deterministic Markdown accuracy metrics used by live extraction benchmarks."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping

_PAGE_BREAK = re.compile(r"<!--\s*PAGE BREAK\s*-->", re.IGNORECASE)
_FIGURE = re.compile(r"<figure\b[^>]*>(.*?)</figure>", re.IGNORECASE | re.DOTALL)
_BOLD_FIELD = re.compile(r"^\*\*([^*\n:]+):\*\*\s*(.+)$")
_LIST_ITEM = re.compile(r"^\s*\d+[.)]\s+(.+)$")


def compare_markdown_accuracy(
    candidate: str,
    expected: str,
    *,
    candidate_types: Mapping[str, str] | None = None,
    expected_types: Mapping[str, str] | None = None,
) -> dict:
    candidate_pages = _PAGE_BREAK.split(candidate)
    expected_pages = _PAGE_BREAK.split(expected)
    page_count = max(len(candidate_pages), len(expected_pages))
    per_page = {
        page_number: _metrics(
            candidate_pages[page_number - 1] if page_number <= len(candidate_pages) else "",
            expected_pages[page_number - 1] if page_number <= len(expected_pages) else "",
        )
        for page_number in range(1, page_count + 1)
    }
    candidate_by_type = candidate_types or {}
    expected_by_type = expected_types or {}
    per_type = {
        content_type: _metrics(
            candidate_by_type.get(content_type, ""), expected_by_type.get(content_type, "")
        )
        for content_type in sorted(candidate_by_type.keys() | expected_by_type.keys())
    }
    return {
        "overall": _metrics(candidate, expected),
        "per_page": per_page,
        "per_type": per_type,
        "minimums": {
            "page_accuracy": min(
                (metrics["strict_word_accuracy"] for metrics in per_page.values()),
                default=1.0,
            ),
            "type_accuracy": min(
                (metrics["strict_word_accuracy"] for metrics in per_type.values()),
                default=1.0,
            ),
        },
    }


def classify_markdown_types(markdown: str) -> dict[str, str]:
    """Split reference Markdown into stable, benchmark-oriented content classes."""
    corpora: dict[str, list[str]] = {
        "text": [],
        "heading": [],
        "list": [],
        "form_field": [],
        "figure": [],
    }

    def take_figure(match: re.Match[str]) -> str:
        value = re.sub(r"<[^>]+>", " ", match.group(1))
        corpora["figure"].append(_plain(value))
        return "\n"

    remaining = _FIGURE.sub(take_figure, markdown)
    for paragraph in re.split(r"\n\s*\n", remaining):
        value = paragraph.strip()
        if not value or _PAGE_BREAK.fullmatch(value):
            continue
        if value.startswith("#"):
            corpora["heading"].append(_plain(re.sub(r"^#+\s*", "", value)))
            continue
        field = _BOLD_FIELD.fullmatch(value)
        if field:
            corpora["form_field"].append(f"{field.group(1)}: {_plain(field.group(2))}")
            continue
        lines = value.splitlines()
        if lines and all(_LIST_ITEM.match(line) for line in lines):
            corpora["list"].extend(
                _plain(match.group(1))
                for line in lines
                if (match := _LIST_ITEM.match(line)) is not None
            )
            continue
        if value.startswith("[") and value.endswith("]"):
            corpora["figure"].append(_plain(value))
            continue
        plain = _plain(value)
        if plain:
            corpora["text"].append(plain)
    return {key: "\n".join(values) for key, values in corpora.items()}


def _plain(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"[*_`>#]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _metrics(candidate: str, expected: str) -> dict[str, float]:
    actual_tokens = _tokens(candidate)
    expected_tokens = _tokens(expected)
    distance = _edit_distance(actual_tokens, expected_tokens)
    word_error_rate = distance / len(expected_tokens) if expected_tokens else float(bool(actual_tokens))
    actual_counts = Counter(actual_tokens)
    expected_counts = Counter(expected_tokens)
    overlap = sum((actual_counts & expected_counts).values())
    precision = overlap / len(actual_tokens) if actual_tokens else float(not expected_tokens)
    recall = overlap / len(expected_tokens) if expected_tokens else float(not actual_tokens)
    token_f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "strict_word_accuracy": max(0.0, 1.0 - word_error_rate),
        "word_error_rate": word_error_rate,
        "token_f1": token_f1,
    }


def _tokens(value: str) -> list[str]:
    value = value.replace("\u00ad", "")
    value = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", value)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.findall(r"\w+", value.casefold(), flags=re.UNICODE)


def _edit_distance(first: list[str], second: list[str]) -> int:
    previous = list(range(len(second) + 1))
    for first_index, first_token in enumerate(first, start=1):
        current = [first_index]
        for second_index, second_token in enumerate(second, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[second_index] + 1,
                    previous[second_index - 1] + (first_token != second_token),
                )
            )
        previous = current
    return previous[-1]


__all__ = ["classify_markdown_types", "compare_markdown_accuracy"]
