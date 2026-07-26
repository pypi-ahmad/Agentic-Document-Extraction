import pytest
from pydantic import ValidationError

from app.services.parsing.v2_contracts import (
    BoundingBox,
    DocumentResult,
    DocumentSplit,
    ExtractionField,
    GroundedChunk,
    Grounding,
    GroundingMethod,
    ProcessingMode,
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
        DocumentResult(
            source_filename="invoice.pdf",
            source_sha256="a" * 64,
            page_count=1,
            markdown='<a id="p0001-c0001"></a>\n\n# Quarterly Report',
            chunks=[_chunk()],
            extraction={"invoice_number": field},
        )


def test_unresolved_field_cannot_expose_an_unsupported_value() -> None:
    with pytest.raises(ValidationError, match="unresolved field value must be null"):
        ExtractionField(value="guess", status="unresolved", citations=[])


def test_document_result_requires_markdown_anchor_for_every_chunk() -> None:
    with pytest.raises(ValidationError, match="missing Markdown anchor"):
        DocumentResult(
            source_filename="report.pdf",
            source_sha256="b" * 64,
            page_count=1,
            markdown="# Quarterly Report",
            chunks=[_chunk()],
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
            source_filename="mixed.pdf",
            source_sha256="d" * 64,
            page_count=1,
            markdown='<a id="p0001-c0001"></a>\n\n# Quarterly Report',
            chunks=[_chunk()],
            splits=[
                DocumentSplit(
                    id="split-1",
                    classification="invoice",
                    identifier="INV-42",
                    pages=[1],
                    chunk_ids=["missing"],
                    boundary_reasons=["start_of_file"],
                )
            ],
        )
