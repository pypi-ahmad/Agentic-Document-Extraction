from app.services.parsing.contracts import (
    BoundingBox,
    DocumentLayout,
    PageLayout,
    Region,
    TableCell,
)
from app.services.parsing.structured_blocks import build_structured_document


def test_structured_document_preserves_hierarchy_provenance_and_cell_grounding() -> None:
    document = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=612,
                height=792,
                coordinate_unit="pdf_points",
                regions=[
                    Region(
                        id="p0001-r0001",
                        type="heading",
                        heading_level=2,
                        bbox=BoundingBox(left=0.1, top=0.05, right=0.9, bottom=0.1),
                        content="Charges",
                        source="paddleocr_vl",
                    ),
                    Region(
                        id="p0001-r0002",
                        type="table",
                        parent_id="p0001-r0001",
                        bbox=BoundingBox(left=0.1, top=0.2, right=0.9, bottom=0.6),
                        content="Item Amount",
                        source="paddleocr_vl",
                        table_cells=[
                            TableCell(
                                bbox=BoundingBox(left=0.1, top=0.2, right=0.5, bottom=0.3),
                                row=0,
                                column=0,
                                text="Item",
                            )
                        ],
                    ),
                ],
            )
        ]
    )

    result = build_structured_document(
        document, source_filename="invoice.pdf", source_sha256="b" * 64
    )

    assert result.schema_version == "paperplane-blocks/v1"
    assert result.blocks[1].parent_id == "p0001-r0001"
    assert result.blocks[1].source_bbox.model_dump() == {
        "left": 61.2,
        "top": 158.4,
        "right": 550.8000000000001,
        "bottom": 475.2,
        "unit": "pdf_points",
    }
    assert result.blocks[1].cells[0].id == "p0001-r0002-c0001"
    assert result.blocks[1].cells[0].parent_id == "p0001-r0002"
    assert result.blocks[1].provenance.parser == "paddleocr_vl"
