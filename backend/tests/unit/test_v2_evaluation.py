from app.services.parsing.contracts import BoundingBox
from app.services.parsing.v2_contracts import (
    DocumentItem,
    DocumentPage,
    DocumentResult,
    Grounding,
    GroundingMethod,
    ItemVerification,
    MarkdownSpan,
    PageDimensions,
    SourceDocument,
    VerificationStatus,
)
from app.services.parsing.v2_evaluation import evaluate_grounded_document


def _document(text: str, *, right: float = 0.8) -> DocumentResult:
    grounding = Grounding(
        page=1,
        box=BoundingBox(left=0.1, top=0.1, right=right, bottom=0.2),
        method=GroundingMethod.VISION_REFINED,
        source_box=(10, 10, 80, 20),
        source_unit="image_pixels",
        evidence_artifact_id="evidence",
    )
    item = DocumentItem(
        id="p0001-c0001",
        order=1,
        type="checkbox",
        text=text,
        markdown_span=MarkdownSpan(start=0, end=len(text)),
        grounding=[grounding],
        verification=ItemVerification(
            status=VerificationStatus.VERIFIED,
            model="gpt-5.6-terra",
            pass_name="page_reconciliation",
        ),
    )
    return DocumentResult(
        source=SourceDocument(filename="form.pdf", sha256="a" * 64, page_count=1),
        status="completed",
        pages=[
            DocumentPage(
                number=1,
                dimensions=PageDimensions(width=100, height=100, unit="image_pixels"),
                verification_status=VerificationStatus.VERIFIED,
                markdown=text,
                items=[item],
            )
        ],
        processing={"mode": "audit"},
    )


def test_evaluation_reports_v3_text_layout_and_structure_metrics() -> None:
    report = evaluate_grounded_document(_document("☒ Approved"), _document("☒ Approved"))

    assert report.schema_version == "paperplane-evaluation/v3"
    assert report.metrics["token_f1"] == 1.0
    assert report.metrics["mean_bbox_iou"] == 1.0
    assert report.metrics["citation_coverage"] == 1.0
    assert report.metrics["checkbox_accuracy"] == 1.0
    assert report.metrics["duplicate_sibling_score"] == 1.0
    assert report.metrics["macro_score"] == 1.0
