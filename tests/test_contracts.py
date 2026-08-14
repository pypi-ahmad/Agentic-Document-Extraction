from __future__ import annotations

import pytest
from pydantic import ValidationError

from paperplane.contracts import (
    AgenticBlockInput,
    AgenticPageInput,
    AtomicLineInput,
    CodepointRange,
    NormalizedBox,
    ParseResponse,
    assemble_parse_response,
)


def _box() -> NormalizedBox:
    return NormalizedBox(left=0.1, top=0.1, right=0.9, bottom=0.2)


def test_assembler_creates_global_unicode_ranges_and_stable_structure_ids() -> None:
    response = assemble_parse_response(
        document_id="doc-42",
        job_id="job-42",
        model="paperplane-ade-latest",
        pages=[
            AgenticPageInput(
                page_number=1,
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="Café",
                        box=_box(),
                        atomic_lines=[AtomicLineInput(text="Café", box=_box())],
                    ),
                    AgenticBlockInput(
                        type="table",
                        markdown="| Item |\n| --- |\n| Thermometer ID |",
                        box=_box(),
                        table_cells=[
                            AgenticBlockInput(
                                type="table_cell",
                                markdown="Item",
                                box=_box(),
                                row=0,
                                col=0,
                            ),
                            AgenticBlockInput(
                                type="table_cell",
                                markdown="Thermometer ID",
                                box=_box(),
                                row=1,
                                col=0,
                            ),
                        ],
                    ),
                ],
            ),
            AgenticPageInput(
                page_number=2,
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="Total Chlorine",
                        box=_box(),
                        semantic_role="paragraph",
                        atomic_lines=[AtomicLineInput(text="Total Chlorine", box=_box())],
                    )
                ],
            ),
        ],
    )

    assert response.markdown == (
        "Café\n\n| Item |\n| --- |\n| Thermometer ID |"
        "\n\n<!-- PAGE BREAK -->\n\nTotal Chlorine\n\n<!-- doc_id=doc-42 -->"
    )
    assert response.metadata.range_units == "unicode_codepoints"
    assert response.metadata.output_characters == len(response.markdown)

    first_page, second_page = response.structure.children
    text_block, table = first_page.children
    assert text_block.id == "text-1"
    assert table.id == "table-1"
    assert [cell.id for cell in table.children] == ["table_cell-1", "table_cell-2"]
    assert second_page.children[0].id == "text-2"
    assert second_page.children[0].semantic_role == "paragraph"
    assert response.markdown[text_block.ranges[0].start : text_block.ranges[0].end] == "Café"
    assert text_block.atomic_grounding[0].ranges == [
        CodepointRange(start=text_block.ranges[0].start, end=text_block.ranges[0].end)
    ]
    assert response.markdown[
        table.children[1].ranges[0].start : table.children[1].ranges[0].end
    ] == ("Thermometer ID")


def test_parse_contract_rejects_overlapping_atomic_grounding_ranges() -> None:
    payload = assemble_parse_response(
        document_id="doc",
        job_id="job",
        model="paperplane-ade-fast-latest",
        pages=[
            AgenticPageInput(
                page_number=1,
                blocks=[
                    AgenticBlockInput(
                        type="text",
                        markdown="alpha beta",
                        box=_box(),
                        atomic_lines=[AtomicLineInput(text="alpha", box=_box())],
                    )
                ],
            )
        ],
    ).model_dump(mode="json")
    block = payload["structure"]["children"][0]["children"][0]
    block["atomic_grounding"].append(
        {
            "text": "alpha beta",
            "box": _box().model_dump(mode="json"),
            "ranges": [{"start": block["ranges"][0]["start"], "end": block["ranges"][0]["end"]}],
        }
    )

    with pytest.raises(ValidationError, match="ordered and non-overlapping"):
        ParseResponse.model_validate(payload)
