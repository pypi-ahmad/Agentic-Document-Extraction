"""Layout + first-pass OCR via a self-hosted GLM-OCR pipeline server.

Talks to the `glmocr[server]` Flask app's ``POST /glmocr/parse`` endpoint
(https://github.com/zai-org/GLM-OCR/blob/main/glmocr/server.py), which runs
PP-DocLayoutV3 layout detection and GLM-OCR recognition together and returns
``json_result: list[page][region]`` with ``{index, label, content, bbox_2d}``
per region, always page-nested (verified against the project's own example
outputs, even for a single input image).

Fidelity note: the server's default ``label_task_mapping`` collapses
PP-DocLayoutV3's 25 raw classes into five OCR task buckets (text, table,
formula, chart, image) and *drops* header/footer/footnote/page-number/
reference regions entirely (its "abandon" bucket). Title/heading distinction
does not survive either — everything textual is "text". This means regions
sourced from this engine carry no heading hierarchy and never include
header/footer/page_number/checkbox/signature/seal types, unlike the richer
(now-removed) PaddleOCR-VL taxonomy. The agentic reflection loop downstream
(confidence gating, cloud visual review) is unaffected by this and still
runs — it just never receives a "low confidence" signal from this engine,
since the server does not return a per-region score.
"""

from __future__ import annotations

import base64
from html.parser import HTMLParser
from pathlib import Path

import httpx

from app.services.parsing.contracts import BoundingBox, Region, RegionType

_LABEL_TO_REGION_TYPE: dict[str, RegionType] = {
    "text": "text",
    "table": "table",
    "formula": "formula",
    "chart": "chart",
    "image": "figure",
}


class GlmOcrUnavailable(RuntimeError):
    pass


class GlmOcrResponseError(RuntimeError):
    pass


class _TableRowParser(HTMLParser):
    """Flatten a GLM-OCR table's raw HTML into a plain text-cell grid.

    ponytail: no rowspan/colspan modeling, no per-cell bbox (the server
    gives one bbox per whole table, not per cell) — upgrade to full
    TableCell grounding if a richer per-cell source becomes available.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.rows.append([])
        elif tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            if self.rows:
                self.rows[-1].append(text)
            self._cell = None


def _table_rows(html: str) -> list[list[str]] | None:
    parser = _TableRowParser()
    try:
        parser.feed(html)
    except Exception:
        return None
    rows = [row for row in parser.rows if row]
    return rows or None


def _region(raw: object) -> Region | None:
    if not isinstance(raw, dict):
        return None
    label = str(raw.get("label") or "text")
    box = raw.get("bbox_2d")
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    left, top, right, bottom = (float(value) / 1000.0 for value in box)
    left, right = max(0.0, min(left, 1.0)), max(0.0, min(right, 1.0))
    top, bottom = max(0.0, min(top, 1.0)), max(0.0, min(bottom, 1.0))
    if right <= left or bottom <= top:
        return None
    content = str(raw.get("content") or "")
    region_type = _LABEL_TO_REGION_TYPE.get(label, "text")
    table_rows = _table_rows(content) if region_type == "table" else None
    return Region(
        type=region_type,
        bbox=BoundingBox(left=left, top=top, right=right, bottom=bottom),
        content=content if region_type != "table" else "",
        source="glmocr",
        source_label=label,
        table_html=content if region_type == "table" else None,
        table_rows=table_rows,
    )


class GlmOcrLayoutEngine:
    """LayoutEngine backed by a self-hosted glmocr pipeline server."""

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self.base_url = base_url.rstrip("/")

    async def segment(self, image_path: Path, device: str = "auto") -> list[Region]:
        del device
        pages = await self._parse([image_path])
        return pages[0] if pages else []

    async def segment_document(
        self,
        *,
        job_id: str,
        image_paths: list[Path],
        page_numbers: list[int],
        work_dir: Path,
    ) -> dict[int, list[Region]]:
        del job_id, work_dir
        if len(image_paths) != len(page_numbers) or not image_paths:
            raise ValueError("GLM-OCR requires matching page images and numbers")
        pages = await self._parse(image_paths)
        if len(pages) != len(page_numbers):
            raise GlmOcrResponseError("GLM-OCR did not return every requested page")
        return dict(zip(page_numbers, pages, strict=True))

    async def _parse(self, image_paths: list[Path]) -> list[list[Region]]:
        images = [
            f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
            for path in image_paths
        ]
        try:
            response = await self._client.post(
                f"{self.base_url}/glmocr/parse", json={"images": images}
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPError as exc:
            raise GlmOcrUnavailable(f"GLM-OCR server request failed: {type(exc).__name__}") from exc
        except ValueError as exc:
            raise GlmOcrResponseError("GLM-OCR server returned an invalid response") from exc
        pages = body.get("json_result") if isinstance(body, dict) else None
        if not isinstance(pages, list):
            raise GlmOcrResponseError("GLM-OCR response is missing json_result")
        return [
            [region for region in (_region(raw) for raw in page) if region is not None]
            if isinstance(page, list)
            else []
            for page in pages
        ]
