from app.services.parsing.contracts import BoundingBox
from app.services.parsing.v2_contracts import (
    DocumentResult,
    GroundedChunk,
    Grounding,
    GroundingMethod,
    VerificationStatus,
)
from app.services.parsing.v2_evaluation import evaluate_grounded_document


def _document(text: str, *, right: float = 0.8) -> DocumentResult:
    chunk = GroundedChunk(
        id="p0001-c0001",
        page=1,
        order=1,
        type="checkbox",
        text=text,
        markdown=text,
        grounding=[
            Grounding(
                page=1,
                box=BoundingBox(left=0.1, top=0.1, right=right, bottom=0.2),
                method=GroundingMethod.VISION_REFINED,
                source_box=(10, 10, 80, 20),
                source_unit="image_pixels",
                evidence_artifact_id="evidence",
            )
        ],
        verification_status=VerificationStatus.VERIFIED,
        source_model="gpt-5.6-terra",
        source_pass="crop_verification",
    )
    return DocumentResult(
        source_filename="form.pdf",
        source_sha256="a" * 64,
        page_count=1,
        markdown=f'<a id="{chunk.id}"></a>\n\n{text}',
        chunks=[chunk],
    )


def test_evaluation_reports_text_layout_citation_and_checkbox_metrics() -> None:
    report = evaluate_grounded_document(_document("☒ Approved"), _document("☒ Approved"))

    assert report.metrics["text_similarity"] == 1.0
    assert report.metrics["mean_bbox_iou"] == 1.0
    assert report.metrics["citation_coverage"] == 1.0
    assert report.metrics["checkbox_accuracy"] == 1.0
    assert report.metrics["macro_score"] == 1.0
