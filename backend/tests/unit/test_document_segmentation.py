from app.services.parsing.contracts import BoundingBox, ContextChunk
from app.services.parsing.segmentation import segment_document


def _chunk(page: int, text: str) -> ContextChunk:
    return ContextChunk(
        id=f"p{page:04d}-r0001",
        ordinal=page,
        page=page,
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.9),
        type="text",
        source="paddleocr_vl",
        markdown=text,
        text=text,
    )


def test_changed_invoice_number_splits_instances_and_repeated_number_joins_pages() -> None:
    segments = segment_document(
        [
            _chunk(1, "Invoice Number: INV-100 Amount Due: $10"),
            _chunk(2, "Invoice Number: INV-100 Payment Terms: Net 30"),
            _chunk(3, "Invoice Number: INV-200 Amount Due: $20"),
        ],
        expected_pages=[1, 2, 3],
    )

    assert [(item.start_page, item.end_page) for item in segments] == [(1, 2), (3, 3)]
    assert segments[0].profile == "invoice"
    assert segments[0].identifiers[0].normalized_value == "INV-100"
    assert "identifier_changed:invoice_number" in segments[1].boundary_reasons


def test_date_change_alone_does_not_split() -> None:
    segments = segment_document(
        [_chunk(1, "Report date: 2026-01-01"), _chunk(2, "Report date: 2026-02-01")],
        expected_pages=[1, 2],
    )

    assert len(segments) == 1


def test_confident_profile_change_splits_mixed_document() -> None:
    segments = segment_document(
        [
            _chunk(1, "Invoice Number: INV-1 Subtotal Amount Due Payment Terms"),
            _chunk(2, "Abstract Methods Results Conclusion DOI 10.1/example References"),
        ],
        expected_pages=[1, 2],
    )

    assert [(item.profile, item.start_page, item.end_page) for item in segments] == [
        ("invoice", 1, 1),
        ("scientific_paper", 2, 2),
    ]


def test_empty_failed_page_is_assigned_and_marked_incomplete() -> None:
    segments = segment_document(
        [_chunk(1, "Invoice Number: INV-1 Amount Due")], expected_pages=[1, 2]
    )

    assert segments[0].end_page == 2
    assert segments[0].complete is False
    assert segments[0].missing_pages == [2]
