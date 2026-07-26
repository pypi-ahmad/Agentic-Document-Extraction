"""Run the official PaddleOCR-VL 1.6 pipeline for one document."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from PIL import Image

EVENT_STREAM = sys.stdout
sys.stdout = sys.stderr

from paddleocr import PaddleOCRVL, TableRecognitionPipelineV2  # noqa: E402


def emit(event: str, page_number: int | None = None, message: str | None = None) -> None:
    payload = {"event": event}
    if page_number is not None:
        payload["page_number"] = page_number
    if message is not None:
        payload["message"] = message[:500]
    print(json.dumps(payload, separators=(",", ":")), file=EVENT_STREAM, flush=True)


def result_json(result: Any) -> dict[str, Any]:
    value = result.json
    if callable(value):
        value = value()
    if not isinstance(value, dict):
        raise TypeError("Paddle result JSON is not an object")
    nested = value.get("res")
    return nested if isinstance(nested, dict) else value


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def refine_tables(
    image_path: Path,
    page_result: dict[str, Any],
    table_pipeline: TableRecognitionPipelineV2 | None,
) -> TableRecognitionPipelineV2 | None:
    blocks = page_result.get("parsing_res_list", [])
    table_blocks = [
        block
        for block in blocks
        if isinstance(block, dict) and "table" in str(block.get("block_label", "")).casefold()
    ]
    if not table_blocks:
        return table_pipeline
    if table_pipeline is None:
        table_pipeline = TableRecognitionPipelineV2(use_layout_detection=False)
    with Image.open(image_path) as image:
        for block in table_blocks:
            box = block.get("block_bbox")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                block.setdefault("warnings", []).append("table_bbox_missing")
                continue
            left, top, right, bottom = (int(float(value)) for value in box)
            crop = image.crop((left, top, right, bottom)).convert("RGB")
            crop_path = (
                Path("/work/output")
                / f"table-{page_result['page_number']}-{block.get('block_id', 0)}.png"
            )
            crop.save(crop_path)
            try:
                table_result = next(iter(table_pipeline.predict(input=str(crop_path))))
                table_json = result_json(table_result)
                table_list = table_json.get("table_res_list")
                if isinstance(table_list, list) and table_list:
                    detail = table_list[0]
                    block["table_refinement"] = {
                        "pred_html": detail.get("pred_html", ""),
                        "cell_box_list": detail.get("cell_box_list", []),
                        "table_ocr_pred": detail.get("table_ocr_pred", {}),
                        "crop_offset": [left, top],
                    }
                else:
                    block.setdefault("warnings", []).append("table_refinement_empty")
            except Exception as exc:  # keep primary Paddle output
                block.setdefault("warnings", []).append(
                    f"table_refinement_failed:{type(exc).__name__}"
                )
            finally:
                crop_path.unlink(missing_ok=True)
    return table_pipeline


def run(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text("utf-8"))
    if manifest.get("pipeline_version") != "v1.6":
        raise ValueError("Unsupported PaddleOCR-VL pipeline version")
    pages = manifest.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("Manifest pages are required")
    pipeline = PaddleOCRVL(
        pipeline_version="v1.6",
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
        use_layout_detection=True,
        use_chart_recognition=True,
        use_seal_recognition=True,
        use_ocr_for_image_block=True,
    )
    table_pipeline = None
    raw_results = []
    page_metadata: list[tuple[int, Path]] = []
    emit("started")
    for item in pages:
        page_number = int(item["page_number"])
        image_path = Path(item["path"])
        prediction = next(iter(pipeline.predict(input=str(image_path))))
        raw_results.append(prediction)
        page_metadata.append((page_number, image_path))
        emit("page_parsed", page_number)

    restructured = list(
        pipeline.restructure_pages(
            raw_results,
            merge_tables=True,
            relevel_titles=True,
            concatenate_pages=False,
        )
    )
    if len(restructured) != len(page_metadata):
        raise RuntimeError("PaddleOCR-VL returned an unexpected page count")
    output_pages = []
    for prediction, (page_number, image_path) in zip(restructured, page_metadata, strict=True):
        page = result_json(prediction)
        page["page_number"] = page_number
        page["width"], page["height"] = image_size(image_path)
        table_pipeline = refine_tables(image_path, page, table_pipeline)
        output_pages.append(page)
        emit("page_refined", page_number)
    output = {
        "schema_version": "1",
        "pipeline_version": "v1.6",
        "pages": output_pages,
    }
    target = Path(manifest["output_path"])
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False), "utf-8")
    temporary.replace(target)
    emit("completed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.manifest)
    except Exception as error:
        emit("error", message=f"{type(error).__name__}: {error}")
        sys.exit(1)
