from app.services.evaluation import GroundTruthDocument, evaluate_document
from app.services.parsing.contracts import BoundingBox, DocumentLayout, PageLayout, Region
from app.services.parsing.segmentation import DetectedSubDocument


def _layout(text: str = "Revenue grew") -> DocumentLayout:
    return DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=1,
                height=1,
                regions=[
                    Region(
                        id="title",
                        type="title",
                        heading_level=1,
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
                        content="Report",
                    ),
                    Region(
                        id="body",
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.3, right=0.9, bottom=0.5),
                        content=text,
                    ),
                ],
            )
        ]
    )


def _gold() -> GroundTruthDocument:
    return GroundTruthDocument.model_validate(
        {
            "schema_version": "paperplane-ground-truth/v1",
            "document_id": "report",
            "markdown": "# Report\n\nRevenue grew\n",
            "pages": [
                {
                    "page": 1,
                    "regions": [
                        {
                            "id": "title",
                            "type": "title",
                            "order": 0,
                            "bbox": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.2},
                            "text": "Report",
                            "heading_level": 1,
                        },
                        {
                            "id": "body",
                            "type": "text",
                            "order": 1,
                            "bbox": {"left": 0.1, "top": 0.3, "right": 0.9, "bottom": 0.5},
                            "text": "Revenue grew",
                            "parent_id": "title",
                        },
                    ],
                }
            ],
        }
    )


def test_perfect_grounded_evaluation_scores_one() -> None:
    report = evaluate_document("# Report\n\nRevenue grew\n", _layout(), _gold())

    assert report.matched_regions == 2
    assert all(score == 1.0 for score in report.metrics.values())


def test_evaluation_reports_text_difference() -> None:
    report = evaluate_document("# Report\n\nRevenue fell\n", _layout("Revenue fell"), _gold())

    assert report.metrics["markdown_similarity"] < 1
    assert report.metrics["region_text_similarity"] < 1
    assert report.metrics["region_f1"] == 1


def test_v2_ground_truth_accepts_grounded_table_cells() -> None:
    layout = _layout()
    layout.pages[0].regions.append(
        Region(
            id="table",
            type="table",
            bbox=BoundingBox(left=0.1, top=0.6, right=0.9, bottom=0.9),
            content="A",
            table_rows=[["A"]],
            table_cells=[
                {
                    "id": "table-c0001",
                    "bbox": {"left": 0.1, "top": 0.6, "right": 0.9, "bottom": 0.9},
                    "row": 0,
                    "column": 0,
                    "text": "A",
                }
            ],
        )
    )
    gold_data = _gold().model_dump(mode="json")
    gold_data["schema_version"] = "paperplane-ground-truth/v2"
    gold_data["pages"][0]["regions"].append(
        {
            "id": "table",
            "type": "table",
            "order": 2,
            "bbox": {"left": 0.1, "top": 0.6, "right": 0.9, "bottom": 0.9},
            "text": "A",
            "table_cells": [
                {
                    "id": "table-c0001",
                    "text": "A",
                    "bbox": {"left": 0.1, "top": 0.6, "right": 0.9, "bottom": 0.9},
                }
            ],
        }
    )
    gold = GroundTruthDocument.model_validate(gold_data)

    report = evaluate_document("# Report\n\nRevenue grew\n", layout, gold)

    assert report.metrics["table_cell_f1"] == 1
    assert report.metrics["table_cell_bbox_iou"] == 1


def test_v2_evaluation_scores_subdocument_boundaries_and_classification() -> None:
    gold_data = _gold().model_dump(mode="json")
    gold_data["schema_version"] = "paperplane-ground-truth/v2"
    gold_data["subdocuments"] = [
        {"start_page": 1, "end_page": 1, "profile": "invoice"},
        {"start_page": 2, "end_page": 2, "profile": "scientific_paper"},
    ]
    predicted = [
        DetectedSubDocument(
            ordinal=1,
            start_page=1,
            end_page=1,
            profile="invoice",
            confidence=0.9,
            boundary_confidence=1,
        ),
        DetectedSubDocument(
            ordinal=2,
            start_page=2,
            end_page=2,
            profile="scientific_paper",
            confidence=0.9,
            boundary_confidence=0.9,
        ),
    ]

    report = evaluate_document(
        "# Report\n\nRevenue grew\n",
        _layout(),
        GroundTruthDocument.model_validate(gold_data),
        predicted,
    )

    assert report.metrics["boundary_f1"] == 1
    assert report.metrics["subdocument_page_assignment_accuracy"] == 1
