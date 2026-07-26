import fitz

from app.services.parsing.contracts import BoundingBox
from app.services.parsing.v2_annotations import build_annotated_pdf
from app.services.parsing.v2_contracts import (
    GroundedChunk,
    Grounding,
    GroundingMethod,
    VerificationStatus,
)


def _pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=200, height=300)
    result = document.tobytes()
    document.close()
    return result


def test_annotated_pdf_contains_chunk_label_and_preserves_page_size() -> None:
    chunk = GroundedChunk(
        id="p0001-c0001",
        page=1,
        order=1,
        type="text",
        text="Invoice",
        markdown="Invoice",
        grounding=[
            Grounding(
                page=1,
                box=BoundingBox(left=0.1, top=0.2, right=0.8, bottom=0.3),
                method=GroundingMethod.TEXT_LAYER_EXACT,
                source_box=(20, 60, 160, 90),
                source_unit="pdf_points",
                evidence_artifact_id="page:1",
            )
        ],
        verification_status=VerificationStatus.VERIFIED,
        source_model="gpt-5.6-luna",
        source_pass="page_draft",
    )

    output = build_annotated_pdf(_pdf(), "invoice.pdf", [chunk])

    document = fitz.open(stream=output, filetype="pdf")
    assert document.page_count == 1
    assert document[0].rect == fitz.Rect(0, 0, 200, 300)
    assert "p0001-c0001" in document[0].get_text()
    document.close()
