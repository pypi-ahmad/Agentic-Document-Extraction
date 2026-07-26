import pytest

from app.services.parsing.paddleocr_vl import _regions


def test_normalizes_blocks_and_preserves_reading_order() -> None:
    regions = _regions(
        [
            {
                "block_bbox": [100, 100, 900, 300],
                "block_label": "doc_title",
                "block_content": "Annual report",
                "block_order": 1,
                "score": 0.98,
            },
            {
                "block_bbox": [100, 400, 900, 1000],
                "block_label": "table",
                "block_content": "| A |",
                "block_order": 2,
            },
        ],
        1000,
        2000,
    )

    assert [region.type for region in regions] == ["title", "table"]
    assert regions[0].bbox.model_dump() == {
        "left": 0.1,
        "top": 0.05,
        "right": 0.9,
        "bottom": 0.15,
    }
    assert regions[0].source == "paddleocr_vl"
    assert regions[0].order == 1
    assert regions[0].confidence == pytest.approx(0.98)


def test_invalid_blocks_are_ignored() -> None:
    assert _regions([{"block_label": "text"}, "bad"], 100, 100) == []
