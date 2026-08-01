import json

import pytest

from app.services.parsing.contracts import (
    BoundingBox,
    DocumentLayout,
    PageLayout,
    Region,
    TableCell,
)
from app.services.parsing.schema_extraction import ExtractionScope, extract_schema_instance
from app.services.parsing.schema_models import SchemaModelGeneration
from app.services.parsing.structured_blocks import build_structured_document

SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "invoice_number": {
            "type": "string",
            "x-paperplane-aliases": ["invoice number"],
        },
        "vendor": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string", "x-paperplane-aliases": ["vendor name"]}
            },
            "required": ["name"],
        },
        "line_items": {
            "type": "array",
            "x-paperplane-kind": "table",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "description": {"type": "string", "x-paperplane-aliases": ["item"]},
                    "amount": {"type": "number"},
                },
                "required": ["description", "amount"],
            },
        },
    },
    "required": ["invoice_number", "vendor", "line_items"],
}


def _cell(row: int, column: int, text: str, *, top: float = 0.2) -> TableCell:
    left = 0.1 + column * 0.4
    return TableCell(
        bbox=BoundingBox(left=left, top=top, right=left + 0.35, bottom=top + 0.01),
        row=row,
        column=column,
        text=text,
    )


def _document(row_count: int = 2) -> tuple:
    pages: list[PageLayout] = []
    remaining = row_count
    next_row = 0
    page_number = 1
    while remaining:
        count = min(1000, remaining)
        cells = [_cell(0, 0, "Item"), _cell(0, 1, "Amount")]
        for local_row in range(1, count + 1):
            cells.extend(
                [
                    _cell(local_row, 0, f"Service {next_row}"),
                    _cell(local_row, 1, f"{next_row + 0.5}"),
                ]
            )
            next_row += 1
        related = []
        if page_number > 1:
            related.append(f"p{page_number - 1:04d}-r0001")
        if remaining > count:
            related.append(f"p{page_number + 1:04d}-r0001")
        pages.append(
            PageLayout(
                page_number=page_number,
                source_page_number=page_number + 10,
                width=1000,
                height=2000,
                coordinate_unit="image_pixels",
                regions=[
                    Region(
                        id=f"p{page_number:04d}-r0001",
                        type="table",
                        bbox=BoundingBox(left=0.1, top=0.2, right=0.9, bottom=0.95),
                        content="Item Amount",
                        source="cloud_vlm",
                        table_cells=cells,
                        related_region_ids=related,
                        heading_level=None,
                    )
                ],
            )
        )
        remaining -= count
        page_number += 1
    pages[0].regions.insert(
        0,
        Region(
            id="p0001-r0000",
            type="text",
            bbox=BoundingBox(left=0.1, top=0.02, right=0.9, bottom=0.08),
            content="Invoice Number: INV-42\nVendor Name: Acme Corp",
            source="cloud_vlm",
        ),
    )
    layout = DocumentLayout(pages=pages)
    return layout, build_structured_document(
        layout, source_filename="invoice.pdf", source_sha256="a" * 64
    )


@pytest.mark.asyncio
async def test_schema_extraction_preserves_shape_and_grounding() -> None:
    _, document = _document()

    bundle = await extract_schema_instance(
        document,
        SCHEMA,
        scope=ExtractionScope(start_page=1, end_page=1),
        processing_mode="local_only",
    )

    assert bundle.instance.data["invoice_number"] == "INV-42"
    assert bundle.instance.data["vendor"]["name"] == "Acme Corp"
    assert bundle.instance.data["line_items"][1] == {
        "description": "Service 1",
        "amount": 1.5,
    }
    citation = bundle.instance.grounding["/line_items/1/amount"][0]
    assert citation.cell_id is not None
    assert citation.source_page == 11
    assert citation.source_bbox.unit == "image_pixels"
    assert bundle.instance.validation_errors == []
    assert bundle.instance.complete is True


@pytest.mark.asyncio
async def test_large_continued_table_exports_all_rows_as_grounded_jsonl() -> None:
    _, document = _document(3000)

    bundle = await extract_schema_instance(
        document,
        SCHEMA,
        scope=ExtractionScope(start_page=1, end_page=3),
        processing_mode="local_only",
    )

    rows = bundle.instance.data["line_items"]
    assert len(rows) == 3000
    assert rows[0]["description"] == "Service 0"
    assert rows[-1]["amount"] == 2999.5
    lines = bundle.table_jsonl["/line_items"].decode().splitlines()
    assert len(lines) == 3000
    last = json.loads(lines[-1])
    assert last["row_index"] == 2999
    assert last["grounding"]["/amount"][0]["source_page"] == 13


@pytest.mark.asyncio
async def test_missing_required_values_are_reported_without_losing_partial_data() -> None:
    layout = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                regions=[
                    Region(
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        content="Invoice Number: INV-1",
                    )
                ],
            )
        ]
    )
    document = build_structured_document(
        layout, source_filename="partial.pdf", source_sha256="b" * 64
    )

    bundle = await extract_schema_instance(
        document,
        SCHEMA,
        scope=ExtractionScope(start_page=1, end_page=1),
        processing_mode="local_only",
    )

    assert bundle.instance.data == {"invoice_number": "INV-1"}
    assert bundle.instance.complete is False
    assert any(error.instance_path == "/" for error in bundle.instance.validation_errors)


class _Model:
    def __init__(self, evidence_id: str) -> None:
        self.evidence_id = evidence_id
        self.prompts: list[str] = []

    async def generate(self, **kwargs) -> SchemaModelGeneration:
        self.prompts.append(kwargs["prompt"])
        return SchemaModelGeneration(
            data={"invoice_number": "MODEL-7"},
            evidence={"/invoice_number": [self.evidence_id]},
            confidence={"/invoice_number": 0.91},
            input_tokens=10,
            output_tokens=4,
            latency_ms=2,
        )


@pytest.mark.asyncio
async def test_model_fills_unresolved_field_only_with_trusted_evidence() -> None:
    layout = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                regions=[
                    Region(
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        content="Reference value",
                    )
                ],
            )
        ]
    )
    document = build_structured_document(layout, source_filename="x.pdf", source_sha256="d" * 64)
    model = _Model("p0001-r0001")
    schema = {
        "type": "object",
        "properties": {"invoice_number": {"type": "string"}},
        "required": ["invoice_number"],
        "additionalProperties": False,
    }

    bundle = await extract_schema_instance(
        document,
        schema,
        scope=ExtractionScope(start_page=1, end_page=1),
        processing_mode="hybrid",
        model_client=model,  # type: ignore[arg-type]
        model_provider="openai",
        model_name="test-model",
    )

    assert bundle.instance.data["invoice_number"] == "MODEL-7"
    assert bundle.instance.grounding["/invoice_number"][0].region_id == "p0001-r0001"
    assert bundle.instance.methods["/invoice_number"] == "model"
    assert bundle.instance.complete is True
    assert len(bundle.instance.model_runs) == 1


@pytest.mark.asyncio
async def test_unknown_model_evidence_is_rejected_and_maximum_accuracy_is_blind() -> None:
    layout = DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=100,
                height=100,
                regions=[
                    Region(
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        content="Reference MODEL-7",
                    )
                ],
            )
        ]
    )
    layout.pages[0].regions[0].content = "Reference value"
    document = build_structured_document(layout, source_filename="x.pdf", source_sha256="e" * 64)
    model = _Model("invented-id")
    schema = {
        "type": "object",
        "properties": {"invoice_number": {"type": "string"}},
        "required": ["invoice_number"],
        "additionalProperties": False,
    }

    bundle = await extract_schema_instance(
        document,
        schema,
        scope=ExtractionScope(start_page=1, end_page=1),
        processing_mode="maximum_accuracy",
        model_client=model,  # type: ignore[arg-type]
        model_provider="openai",
        model_name="test-model",
    )

    assert "/invoice_number" not in bundle.instance.grounding
    assert bundle.instance.complete is False
    assert len(model.prompts) == 2
    assert "independent blind verification" in model.prompts[1].casefold()
    assert "MODEL-7" not in model.prompts[1]


def test_model_pointer_writer_supports_nested_arrays() -> None:
    from app.services.parsing.schema_extraction import _set_pointer

    data: dict = {}
    _set_pointer(data, "/claims/0/lines/0/code", "A100")
    _set_pointer(data, "/claims/0/lines/1/code", "B200")

    assert data == {
        "claims": [{"lines": [{"code": "A100"}, {"code": "B200"}]}]
    }
