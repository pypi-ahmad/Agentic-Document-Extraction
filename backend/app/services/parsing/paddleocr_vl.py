"""Normalize official PaddleOCR-VL worker results."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

from app.services.parsing.contracts import BoundingBox, Region, RegionType, TableCell


class PaddleOCRVLError(RuntimeError):
    """Base failure raised by the PaddleOCR-VL boundary."""


class PaddleOCRVLUnavailable(PaddleOCRVLError):
    """The PaddleOCR-VL service could not process a request."""


class PaddleOCRVLResponseError(PaddleOCRVLError):
    """The PaddleOCR-VL service returned an invalid response."""


def _regions(blocks: list[Any], width: int, height: int) -> list[Region]:
    regions: list[Region] = []
    for index, raw in enumerate(blocks):
        if not isinstance(raw, dict):
            continue
        box = raw.get("block_bbox") or raw.get("bbox") or raw.get("coordinate")
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        left, top, right, bottom = (float(value) for value in box)
        normalized = {
            "left": max(0.0, min(left / width, 1.0)),
            "top": max(0.0, min(top / height, 1.0)),
            "right": max(0.0, min(right / width, 1.0)),
            "bottom": max(0.0, min(bottom / height, 1.0)),
        }
        if normalized["right"] <= normalized["left"] or normalized["bottom"] <= normalized["top"]:
            continue
        score = raw.get("score")
        confidence = float(score) if isinstance(score, (int, float)) and 0 <= score <= 1 else None
        raw_order = raw.get("block_order", raw.get("block_id", index))
        order = int(raw_order) if isinstance(raw_order, (int, float)) and raw_order >= 0 else index
        table_html, table_cells, table_warnings = _table_metadata(raw, width, height)
        raw_warnings = raw.get("warnings")
        warnings = [str(item) for item in raw_warnings] if isinstance(raw_warnings, list) else []
        source_label = str(raw.get("block_label") or raw.get("label") or "text")
        regions.append(
            Region(
                type=_region_type(source_label),
                bbox=BoundingBox(**normalized),
                content=str(raw.get("block_content") or raw.get("content") or "").strip(),
                source="paddleocr_vl",
                source_label=source_label,
                heading_level=_heading_level(source_label, raw),
                order=order,
                confidence=confidence,
                warnings=[*warnings, *table_warnings],
                table_html=table_html,
                table_cells=table_cells,
            )
        )
    return regions


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cells: list[dict[str, Any]] = []
        self.row = -1
        self.column = 0
        self._cell: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.row += 1
            self.column = 0
        elif tag in {"td", "th"}:
            values = dict(attrs)
            self._cell = {
                "text": [],
                "row": max(self.row, 0),
                "column": self.column,
                "rowspan": _positive_int(values.get("rowspan")),
                "colspan": _positive_int(values.get("colspan")),
            }

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell["text"].append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            self._cell["text"] = " ".join("".join(self._cell["text"]).split())
            self.cells.append(self._cell)
            self.column += int(self._cell["colspan"])
            self._cell = None


def _positive_int(value: str | None) -> int:
    try:
        return max(1, int(value or "1"))
    except ValueError:
        return 1


def _table_metadata(
    raw: dict[str, Any], width: int, height: int
) -> tuple[str | None, list[TableCell], list[str]]:
    refinement = raw.get("table_refinement")
    if not isinstance(refinement, dict):
        return None, [], []
    html = refinement.get("pred_html")
    boxes = refinement.get("cell_box_list")
    offset = refinement.get("crop_offset", [0, 0])
    if not isinstance(html, str) or not html.strip() or not isinstance(boxes, list):
        return html if isinstance(html, str) else None, [], ["table_refinement_invalid"]
    parser = _TableHTMLParser()
    try:
        parser.feed(html)
    except Exception:
        return html, [], ["table_html_invalid"]
    if len(parser.cells) != len(boxes):
        return html, [], ["table_cell_count_mismatch"]
    offset_x, offset_y = (
        (float(offset[0]), float(offset[1]))
        if isinstance(offset, (list, tuple)) and len(offset) == 2
        else (0.0, 0.0)
    )
    cells: list[TableCell] = []
    for cell, box in zip(parser.cells, boxes, strict=True):
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            return html, [], ["table_cell_bbox_invalid"]
        left, top, right, bottom = (float(value) for value in box)
        try:
            bbox = BoundingBox(
                left=max(0.0, min((left + offset_x) / width, 1.0)),
                top=max(0.0, min((top + offset_y) / height, 1.0)),
                right=max(0.0, min((right + offset_x) / width, 1.0)),
                bottom=max(0.0, min((bottom + offset_y) / height, 1.0)),
            )
        except ValueError:
            return html, [], ["table_cell_bbox_invalid"]
        cells.append(TableCell(bbox=bbox, **cell))
    return html, cells, []


def _region_type(label: str) -> RegionType:
    label = label.casefold()
    if label in {"doc_title", "document_title"}:
        return "title"
    if "title" in label:
        return "heading"
    if "header" in label:
        return "header"
    if "footer" in label or "footnote" in label:
        return "footer"
    if label in {"number", "page_number"}:
        return "page_number"
    if "table" in label:
        return "table"
    if "chart" in label:
        return "chart"
    if "figure" in label or "image" in label:
        return "figure"
    if "formula" in label or "equation" in label:
        return "formula"
    if "checkbox" in label or "check_box" in label:
        return "checkbox"
    if "signature" in label:
        return "signature"
    if "seal" in label or "stamp" in label:
        return "seal"
    if "form" in label or "key_value" in label:
        return "form_field"
    if "list" in label or "reference" in label:
        return "list"
    if "code" in label or "algorithm" in label:
        return "code"
    return "text"


def _heading_level(label: str, raw: dict[str, Any]) -> int | None:
    explicit = raw.get("heading_level") or raw.get("level")
    if isinstance(explicit, (int, float)) and 1 <= int(explicit) <= 6:
        return int(explicit)
    normalized = label.casefold()
    if normalized in {"doc_title", "document_title"}:
        return 1
    if "title" in normalized:
        match = re.search(r"(?:level|heading|title)[_-]?(\d)", normalized)
        if match:
            return min(max(int(match.group(1)), 2), 6)
        content = str(raw.get("block_content") or raw.get("content") or "").lstrip()
        markdown = re.match(r"^(#{1,6})\s", content)
        if markdown:
            return len(markdown.group(1))
        numbered = re.match(r"^\d+(?:\.\d+)+[.)]?\s", content)
        if numbered:
            return min(numbered.group(0).count(".") + 2, 6)
        return 2
    return None
