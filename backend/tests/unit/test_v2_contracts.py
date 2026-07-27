import pytest
from pydantic import ValidationError

from app.services.parsing.v2_contracts import (
    BoundingBox,
    DocumentItem,
    DocumentPage,
    DocumentResult,
    DocumentSplit,
    ExtractionField,
    GroundedChunk,
    Grounding,
    GroundingMethod,
    ItemVerification,
    MarkdownSpan,
    PageDimensions,
    ProcessingMode,
    QualitySummary,
    SchemaExtraction,
    SourceDocument,
    VerificationStatus,
    mode_policy,
)


def _grounding() -> Grounding:
    return Grounding(
        page=1,
        box=BoundingBox(left=0.1, top=0.2, right=0.8, bottom=0.4),
        method=GroundingMethod.TEXT_LAYER_EXACT,
        source_box=[61.2, 158.4, 489.6, 316.8],
        source_unit="pdf_points",
        evidence_artifact_id="crop-p1-title",
    )


def _chunk() -> GroundedChunk:
    return GroundedChunk(
        id="p0001-c0001",
        page=1,
        order=1,
        type="heading",
        text="Quarterly Report",
        markdown="# Quarterly Report",
        grounding=[_grounding()],
        verification_status=VerificationStatus.VERIFIED,
        source_model="gpt-5.6-luna",
        source_pass="page_draft",
    )


def _item() -> DocumentItem:
    return DocumentItem(
        id="p0001-c0001",
        order=1,
        type="heading",
        text="Quarterly Report",
        markdown_span=MarkdownSpan(start=0, end=18),
        grounding=[_grounding()],
        verification=ItemVerification(
            status=VerificationStatus.VERIFIED,
            model="gpt-5.6-luna",
            pass_name="page_draft",
        ),
    )


def _document(*, extraction: SchemaExtraction | None = None) -> DocumentResult:
    return DocumentResult(
        source=SourceDocument(
            filename="invoice.pdf",
            sha256="a" * 64,
            mime_type="application/pdf",
            page_count=1,
        ),
        status="completed",
        quality_summary=QualitySummary(verified_items=1),
        pages=[
            DocumentPage(
                number=1,
                dimensions=PageDimensions(width=612, height=792, unit="pdf_points"),
                verification_status=VerificationStatus.VERIFIED,
                markdown="# Quarterly Report",
                items=[_item()],
            )
        ],
        extraction=extraction,
        processing={"mode": "balanced"},
    )


def test_verified_chunk_requires_visual_or_text_layer_evidence() -> None:
    with pytest.raises(ValidationError, match="verified chunk requires grounding"):
        GroundedChunk(
            id="p0001-c0001",
            page=1,
            order=1,
            type="text",
            text="Unsupported claim",
            markdown="Unsupported claim",
            verification_status=VerificationStatus.VERIFIED,
            source_model="gpt-5.6-luna",
            source_pass="page_draft",
        )


def test_grounded_field_requires_citations_to_existing_chunks() -> None:
    field = ExtractionField(value="ACME-42", status="grounded", citations=["missing"])

    with pytest.raises(ValidationError, match="unknown citation"):
        _document(
            extraction=SchemaExtraction(
                data={"invoice_number": "ACME-42"}, fields={"invoice_number": field}
            )
        )


def test_unresolved_field_cannot_expose_an_unsupported_value() -> None:
    with pytest.raises(ValidationError, match="unresolved field value must be null"):
        ExtractionField(value="guess", status="unresolved", citations=[])


def test_document_result_uses_page_spans_without_global_markdown_or_chunks() -> None:
    document = _document()

    payload = document.model_dump(mode="json", by_alias=True)

    assert payload["schema_version"] == "paperplane-document/v3"
    assert "markdown" not in payload
    assert "chunks" not in payload
    assert payload["pages"][0]["items"][0]["markdown_span"] == {"start": 0, "end": 18}


def test_document_item_span_must_fit_its_page_markdown() -> None:
    page = _document().pages[0].model_copy(deep=True)
    page.items[0].markdown_span.end = 999

    with pytest.raises(ValidationError, match="markdown span"):
        DocumentResult(
            source=SourceDocument(
                filename="report.pdf",
                sha256="b" * 64,
                mime_type="application/pdf",
                page_count=1,
            ),
            status="completed",
            pages=[page],
            processing={"mode": "balanced"},
        )


def test_processing_modes_have_bounded_inspection_budgets() -> None:
    assert mode_policy(ProcessingMode.ECONOMY).max_repair_rounds == 1
    assert mode_policy(ProcessingMode.ECONOMY).terra_scope == "none"
    assert mode_policy(ProcessingMode.BALANCED).base_dpi == 200
    assert mode_policy(ProcessingMode.BALANCED).terra_reasoning_effort == "medium"
    assert mode_policy(ProcessingMode.AUDIT).max_repair_rounds == 3
    assert mode_policy(ProcessingMode.AUDIT).crop_dpi == 400


def test_document_split_must_reference_known_pages_and_chunks() -> None:
    with pytest.raises(ValidationError, match=r"split .* unknown chunk"):
        DocumentResult(
            source=SourceDocument(
                filename="mixed.pdf",
                sha256="d" * 64,
                mime_type="application/pdf",
                page_count=1,
            ),
            status="completed",
            pages=[_document().pages[0]],
            processing={"mode": "balanced"},
            splits=[
                DocumentSplit(
                    id="split-1",
                    classification="invoice",
                    identifier="INV-42",
                    pages=[1],
                    item_ids=["missing"],
                    boundary_reasons=["start_of_file"],
                )
            ],
        )
