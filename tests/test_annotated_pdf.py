from io import BytesIO

import fitz
from PIL import Image

from paperplane.annotated_pdf import build_annotated_pdf
from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    NormalizedBox,
    assemble_parse_response,
)


def _grounded_response():
    return assemble_parse_response(
        document_id="document",
        job_id="job",
        model="paperplane-ade-latest",
        pages=[
            AgenticPageInput(
                page_number=1,
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="Grounded total: 42",
                        box=NormalizedBox(left=0.1, top=0.1, right=0.8, bottom=0.2),
                    )
                ],
            )
        ],
    )


def _pdf() -> bytes:
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((30, 60), "Grounded total: 42")
    data = document.tobytes()
    document.close()
    return data


def test_build_annotated_pdf_overlays_grounded_source() -> None:
    artifact = build_annotated_pdf(
        source=_pdf(), filename="source.pdf", response=_grounded_response()
    )

    document = fitz.open(stream=artifact.data, filetype="pdf")
    try:
        assert artifact.kind == "source_overlay"
        assert artifact.annotated_blocks == 1
        assert "text-1 | text" in document[0].get_text()
        assert document[0].get_drawings()
    finally:
        document.close()


def test_build_annotated_pdf_converts_image_to_reviewable_pdf() -> None:
    output = BytesIO()
    Image.new("RGB", (200, 100), "white").save(output, format="PNG")

    artifact = build_annotated_pdf(
        source=output.getvalue(), filename="source.png", response=_grounded_response()
    )

    document = fitz.open(stream=artifact.data, filetype="pdf")
    try:
        assert document.page_count == 1
        assert document[0].rect.width == 200
        assert document[0].rect.height == 100
    finally:
        document.close()


def test_build_annotated_pdf_reports_semantic_only_office_blocks() -> None:
    response = assemble_parse_response(
        document_id="document",
        job_id="job",
        model="paperplane-ade-latest",
        pages=[
            AgenticPageInput(
                page_number=None,
                parser="docling",
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="Office content",
                        grounding_status="semantic_only",
                    )
                ],
            )
        ],
        engine="docling",
    )

    artifact = build_annotated_pdf(source=b"office", filename="source.docx", response=response)

    document = fitz.open(stream=artifact.data, filetype="pdf")
    try:
        text = "".join(page.get_text() for page in document)
        assert artifact.kind == "semantic_report"
        assert artifact.semantic_blocks == 1
        assert "semantic_only" in text
        assert "Office content" in text
    finally:
        document.close()
