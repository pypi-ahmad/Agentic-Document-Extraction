from app.services.parsing.contracts import BoundingBox, ContextChunk
from app.services.parsing.domain_extraction import extract_domain


def _chunk(region_id: str, page: int, text: str) -> ContextChunk:
    return ContextChunk(
        id=region_id,
        ordinal=page,
        page=page,
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
        type="text",
        source="paddleocr_vl",
        markdown=text,
        text=text,
    )


def test_invoice_extraction_is_grounded_and_reports_missing_pages() -> None:
    result = extract_domain(
        [
            _chunk("p0001-r0001", 1, "Invoice Number: INV-42"),
            _chunk("p0001-r0002", 1, "Grand Total: USD 125.00"),
        ],
        "auto",
        expected_pages=[1, 2],
    )

    assert result.detected_profile == "invoice"
    assert result.complete is False
    assert result.missing_pages == [2]
    assert result.fields["invoice_number"].value == "INV-42"
    assert result.fields["invoice_number"].evidence[0].region_id == "p0001-r0001"
    assert result.schema_version == "paperplane-domain-extraction/v2"
    assert result.fields["invoice_number"].method == "rule"
    assert result.fields["invoice_number"].candidates[0]["method"] == "label_match"


def test_profile_override_is_respected() -> None:
    result = extract_domain(
        [_chunk("p0001-r0001", 1, "Abstract: A study")],
        "technical_document",
        expected_pages=[1],
    )

    assert result.detected_profile == "technical_document"
    assert result.classification_confidence == 1
