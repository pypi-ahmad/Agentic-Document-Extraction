import pytest

from app.services.parsing.v2_accuracy import (
    classify_markdown_types,
    compare_markdown_accuracy,
)


def test_accuracy_report_keeps_figure_text_and_scores_pages_and_types() -> None:
    candidate = (
        "Hello world\n\n<!-- PAGE BREAK -->\n\n"
        '<figure type="ILLUSTRATION"><description>A blue bottle.</description></figure>'
    )
    expected = (
        "Hello brave world\n\n<!-- PAGE BREAK -->\n\n"
        '<figure type="ILLUSTRATION"><description>A red bottle.</description></figure>'
    )

    report = compare_markdown_accuracy(
        candidate,
        expected,
        candidate_types={"text": "Hello world", "figure": "A blue bottle."},
        expected_types={"text": "Hello brave world", "figure": "A red bottle."},
    )

    assert report["overall"]["strict_word_accuracy"] == pytest.approx(2 / 3)
    assert report["overall"]["word_error_rate"] == pytest.approx(1 / 3)
    assert report["overall"]["token_f1"] == pytest.approx(8 / 11)
    assert report["per_page"][1]["strict_word_accuracy"] == pytest.approx(2 / 3)
    assert report["per_page"][2]["strict_word_accuracy"] == pytest.approx(2 / 3)
    assert report["per_type"]["text"]["strict_word_accuracy"] == pytest.approx(2 / 3)
    assert report["per_type"]["figure"]["strict_word_accuracy"] == pytest.approx(2 / 3)
    assert report["minimums"] == pytest.approx({"page_accuracy": 2 / 3, "type_accuracy": 2 / 3})


def test_accuracy_normalization_ignores_markdown_punctuation_case_and_spacing() -> None:
    report = compare_markdown_accuracy("## SAMPLE—TITLE", "sample title")

    assert report["overall"] == {
        "strict_word_accuracy": 1.0,
        "word_error_rate": 0.0,
        "token_f1": 1.0,
    }


def test_classify_markdown_types_builds_the_five_benchmark_corpora() -> None:
    markdown = """# Sample title

Ordinary body copy.

1. First procedure step.

**County:** Enter the county name.

<figure type="ILLUSTRATION">
<description>A bottle between two fill lines.</description>
</figure>
"""

    corpora = classify_markdown_types(markdown)

    assert corpora == {
        "text": "Ordinary body copy.",
        "heading": "Sample title",
        "list": "First procedure step.",
        "form_field": "County: Enter the county name.",
        "figure": "A bottle between two fill lines.",
    }
