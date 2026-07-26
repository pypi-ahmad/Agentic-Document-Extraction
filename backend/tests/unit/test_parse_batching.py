from app.services.parsing.worker import _mark_missing_pages, _page_batches


def test_page_batches_are_capped_at_ten_and_keep_gaps_separate() -> None:
    pages = [*range(1, 22), 25, 26]

    assert _page_batches(pages, 10) == [
        list(range(1, 11)),
        list(range(11, 21)),
        [21],
        [25, 26],
    ]


def test_partial_markdown_is_never_silent() -> None:
    output = _mark_missing_pages("# Result\n", [11, 12])

    assert "Incomplete document" in output
    assert "11, 12" in output
