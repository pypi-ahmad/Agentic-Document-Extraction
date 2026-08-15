"""Local layout detection and model-specific prompts for Ollama OCR models."""

from __future__ import annotations

import argparse
import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
from io import BytesIO
from typing import Protocol

from PIL import Image

from paperplane.model_store import ModelStore, prepare_model_store

LAYOUT_THRESHOLD = 0.3
MAX_REGIONS_PER_PAGE = 256


@dataclass(frozen=True, slots=True)
class LayoutRegion:
    label: str
    score: float
    left: float
    top: float
    right: float
    bottom: float


class LayoutDetector(Protocol):
    def detect(self, image_png: bytes) -> list[LayoutRegion]: ...


@dataclass(frozen=True, slots=True)
class OcrProfile:
    family: str

    def prompt_for(self, label: str) -> str:
        normalized = label.casefold()
        if self.family == "glmocr":
            if "table" in normalized:
                return "Table Recognition:"
            if "formula" in normalized:
                return "Formula Recognition:"
            if normalized in {"chart", "image", "seal"}:
                return "Figure Recognition:"
            return "Text Recognition:"
        if self.family == "deepseekocr":
            if normalized in {"chart", "image", "seal"}:
                return "Parse the figure."
            if "table" in normalized or "formula" in normalized:
                return "<|grounding|>Convert the document to markdown."
            return "Free OCR."
        return "OCR:"


def profile_for_family(family: str | None) -> OcrProfile | None:
    normalized = (family or "").casefold()
    if normalized in {"glmocr", "paddleocr", "deepseekocr"}:
        return OcrProfile(normalized)
    return None


def chunk_type_for_label(label: str) -> str:
    normalized = label.casefold()
    if normalized == "doc_title":
        return "title"
    if normalized in {"paragraph_title", "section_title"}:
        return "heading"
    if "table" in normalized:
        return "table"
    if normalized == "chart":
        return "chart"
    if normalized in {"image", "seal"}:
        return "figure"
    if "header" in normalized:
        return "header"
    if normalized in {"footer", "page_number"}:
        return "footer"
    return "text"


_CONTROL_TOKEN = re.compile(r"<\|(?:im_end|md_continue|endofsentence)\|>")
_MARKDOWN_BLOCK = re.compile(r"<\|md_start\|>(.*?)<\|md_end\|>", re.DOTALL)


def clean_ocr_output(value: str) -> str:
    blocks = [block.strip() for block in _MARKDOWN_BLOCK.findall(value) if block.strip()]
    if blocks:
        deduplicated: list[str] = []
        for block in blocks:
            if not deduplicated or block != deduplicated[-1]:
                deduplicated.append(block)
        value = "\n\n".join(deduplicated)
    value = _CONTROL_TOKEN.sub("", value).strip()
    if value.startswith("```") and value.endswith("```"):
        value = re.sub(r"^```(?:markdown|md|html|text)?\s*", "", value, count=1)
        value = re.sub(r"\s*```$", "", value, count=1)
    lines: list[str] = []
    seen_nonempty: list[str] = []
    for line in value.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"```(?:markdown|md|html|text)?", stripped):
            continue
        if stripped:
            normalized = stripped.casefold()
            if normalized.startswith(
                (
                    "type the text:",
                    "is there any text that can be recognized",
                    "answer the following question",
                )
            ):
                break
            if any(
                normalized == previous
                or (
                    min(len(normalized), len(previous)) >= 40
                    and (
                        normalized.startswith(previous)
                        or previous.startswith(normalized)
                        or SequenceMatcher(None, normalized, previous).ratio() >= 0.9
                    )
                )
                for previous in seen_nonempty
            ):
                continue
            seen_nonempty.append(normalized)
        if not lines or stripped != lines[-1].strip():
            lines.append(line)
    return "\n".join(lines).strip()


def crop_region(image_png: bytes, region: LayoutRegion, padding: float = 0.05) -> bytes:
    with Image.open(BytesIO(image_png)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        region_width = region.right - region.left
        region_height = region.bottom - region.top
        left = max(0, int((region.left - region_width * padding) * width))
        top = max(0, int((region.top - region_height * padding) * height))
        right = min(width, max(left + 1, int((region.right + region_width * padding) * width)))
        bottom = min(height, max(top + 1, int((region.bottom + region_height * padding) * height)))
        crop = rgb.crop((left, top, right, bottom))
        if region.label.casefold() == "aside_text" and crop.height > crop.width * 2:
            crop = crop.rotate(-90, expand=True)
        output = BytesIO()
        crop.save(output, format="PNG")
        return output.getvalue()


def _overlap_over_smaller(first: LayoutRegion, second: LayoutRegion) -> float:
    width = max(0.0, min(first.right, second.right) - max(first.left, second.left))
    height = max(0.0, min(first.bottom, second.bottom) - max(first.top, second.top))
    intersection = width * height
    first_area = (first.right - first.left) * (first.bottom - first.top)
    second_area = (second.right - second.left) * (second.bottom - second.top)
    smaller = min(first_area, second_area)
    return intersection / smaller if smaller else 0.0


def deduplicate_regions(regions: list[LayoutRegion]) -> list[LayoutRegion]:
    deduplicated: list[LayoutRegion] = []
    for region in regions:
        duplicate = next(
            (
                index
                for index, existing in enumerate(deduplicated)
                if _overlap_over_smaller(region, existing) >= 0.9
            ),
            None,
        )
        if duplicate is None:
            deduplicated.append(region)
        elif region.score > deduplicated[duplicate].score:
            deduplicated[duplicate] = region
    return deduplicated


class PPDocLayoutDetector:
    def __init__(self) -> None:
        import torch
        from transformers import AutoImageProcessor, AutoModelForObjectDetection

        model_path = ModelStore().layout_root
        self._torch = torch
        self._processor = AutoImageProcessor.from_pretrained(model_path, local_files_only=True)
        self._model = AutoModelForObjectDetection.from_pretrained(
            model_path, local_files_only=True
        ).eval()
        self._lock = threading.Lock()

    def detect(self, image_png: bytes) -> list[LayoutRegion]:
        with Image.open(BytesIO(image_png)) as source:
            image = source.convert("RGB")
        width, height = image.size
        inputs = self._processor(images=[image], return_tensors="pt")
        with self._lock, self._torch.inference_mode():
            outputs = self._model(**inputs)
        result = self._processor.post_process_object_detection(
            outputs,
            threshold=LAYOUT_THRESHOLD,
            target_sizes=self._torch.tensor([[height, width]]),
        )[0]
        labels = result["labels"].tolist()
        scores = result["scores"].tolist()
        boxes = result["boxes"].tolist()
        id_to_label = self._model.config.id2label
        regions = deduplicate_regions(
            [
                LayoutRegion(
                    label=str(id_to_label.get(int(label), label)),
                    score=float(score),
                    left=max(0.0, min(float(box[0]) / width, 1.0)),
                    top=max(0.0, min(float(box[1]) / height, 1.0)),
                    right=max(0.0, min(float(box[2]) / width, 1.0)),
                    bottom=max(0.0, min(float(box[3]) / height, 1.0)),
                )
                for label, score, box in zip(labels, scores, boxes, strict=True)
                if box[2] > box[0] and box[3] > box[1]
            ]
        )
        if len(regions) > MAX_REGIONS_PER_PAGE:
            raise RuntimeError(
                f"PP-DocLayoutV3 returned {len(regions)} regions; maximum is {MAX_REGIONS_PER_PAGE}"
            )
        return regions


@lru_cache(maxsize=1)
def get_layout_detector() -> PPDocLayoutDetector:
    return PPDocLayoutDetector()


def ensure_layout_model(*, download: bool) -> None:
    status = prepare_model_store(download_missing=download)
    if not status.ready:
        raise RuntimeError("Permanent PP-DocLayoutV3 model files are incomplete")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--download", action="store_true")
    args = parser.parse_args()
    ensure_layout_model(download=bool(args.download))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
