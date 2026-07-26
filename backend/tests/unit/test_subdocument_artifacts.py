import fitz

from app.models.enums import ArtifactType
from app.models.schemas import ParseSettings
from app.services.parsing.contracts import BoundingBox, DocumentLayout, PageLayout, Region
from app.services.parsing.segmentation import DetectedSubDocument
from app.services.parsing.subdocument_artifacts import build_subdocument_payloads


def _source_pdf() -> bytes:
    document = fitz.open()
    for page_number in range(1, 4):
        page = document.new_page(width=300, height=400)
        page.insert_text((30, 50), f"Page {page_number}")
    data = document.tobytes()
    document.close()
    return data


def test_subdocument_exports_selected_pages_and_preserves_source_page_citations() -> None:
    layout = DocumentLayout(
        pages=[
            PageLayout(
                page_number=page,
                width=300,
                height=400,
                coordinate_unit="pdf_points",
                regions=[
                    Region(
                        id=f"p{page:04d}-r0001",
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        content=f"Page {page}",
                        source="paddleocr_vl",
                    )
                ],
            )
            for page in range(1, 4)
        ]
    )
    payloads = build_subdocument_payloads(
        source=_source_pdf(),
        source_filename="mixed.pdf",
        source_sha256="a" * 64,
        layout=layout,
        segment=DetectedSubDocument(
            ordinal=1,
            start_page=2,
            end_page=3,
            profile="general_scanned",
            confidence=0.5,
            boundary_confidence=1,
        ),
        settings=ParseSettings(searchable_pdf=False, bundle=False),
        figure_crops={},
    )
    by_type = {kind: data for kind, _, data, _, _ in payloads}

    split_pdf = fitz.open(stream=by_type[ArtifactType.SOURCE_DOCUMENT], filetype="pdf")
    assert split_pdf.page_count == 2
    split_pdf.close()
    llm_markdown = by_type[ArtifactType.LLM_MARKDOWN].decode()
    assert '"page":1,"source_page":2' in llm_markdown
    assert '"page":2,"source_page":3' in llm_markdown
