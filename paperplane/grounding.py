"""Deterministic rendering and coordinate transforms for V2 grounding."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image

from paperplane.ingest import DocumentInputError
from paperplane.types import BoundingBox, NativeWord


@dataclass(frozen=True)
class RenderedCrop:
    page_number: int
    image_png: bytes
    page_box: BoundingBox
    source_box: tuple[float, float, float, float]
    source_unit: str


def _token(value: str) -> str:
    return re.sub(r"\W+", "", value, flags=re.UNICODE).casefold()


def align_text_to_native_words(text: str, words: list[NativeWord]) -> BoundingBox | None:
    """Return the exact union of a contiguous native-word match."""
    wanted = [_token(item) for item in text.split()]
    wanted = [item for item in wanted if item]
    available = [_token(word.text) for word in words]
    if not wanted or len(wanted) > len(available):
        return None
    for start in range(len(available) - len(wanted) + 1):
        if available[start : start + len(wanted)] != wanted:
            continue
        matched = words[start : start + len(wanted)]
        return BoundingBox(
            left=min(word.bbox.left for word in matched),
            top=min(word.bbox.top for word in matched),
            right=max(word.bbox.right for word in matched),
            bottom=max(word.bbox.bottom for word in matched),
        )
    return None


def map_crop_box_to_page(crop: BoundingBox, relative: BoundingBox) -> BoundingBox:
    width = crop.right - crop.left
    height = crop.bottom - crop.top
    return BoundingBox(
        left=round(crop.left + relative.left * width, 8),
        top=round(crop.top + relative.top * height, 8),
        right=round(crop.left + relative.right * width, 8),
        bottom=round(crop.top + relative.bottom * height, 8),
    )


def _padded_box(box: BoundingBox, padding: float) -> BoundingBox:
    return BoundingBox(
        left=max(0.0, box.left - padding),
        top=max(0.0, box.top - padding),
        right=min(1.0, box.right + padding),
        bottom=min(1.0, box.bottom + padding),
    )


def render_crop(
    data: bytes,
    filename: str,
    *,
    page_number: int,
    box: BoundingBox,
    dpi: int,
    padding: float = 0.0,
) -> RenderedCrop:
    if page_number < 1:
        raise DocumentInputError("invalid_page", "Page numbers are one-based")
    page_box = _padded_box(box, padding)
    if Path(filename).suffix.lower() == ".pdf":
        document = fitz.open(stream=data, filetype="pdf")
        try:
            if page_number > document.page_count:
                raise DocumentInputError("invalid_page", "Page is outside the document")
            page = document[page_number - 1]
            width, height = float(page.rect.width), float(page.rect.height)
            source_box = (
                page_box.left * width,
                page_box.top * height,
                page_box.right * width,
                page_box.bottom * height,
            )
            clip = fitz.Rect(*source_box)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), clip=clip, alpha=False)
            return RenderedCrop(
                page_number=page_number,
                image_png=pixmap.tobytes("png"),
                page_box=page_box,
                source_box=source_box,
                source_unit="pdf_points",
            )
        finally:
            document.close()

    with Image.open(BytesIO(data)) as image:
        frame_count = int(getattr(image, "n_frames", 1))
        if page_number > frame_count:
            raise DocumentInputError("invalid_page", "Page is outside the image")
        image.seek(page_number - 1)
        rgb = image.convert("RGB")
        source_box = (
            page_box.left * rgb.width,
            page_box.top * rgb.height,
            page_box.right * rgb.width,
            page_box.bottom * rgb.height,
        )
        cropped = rgb.crop(tuple(round(item) for item in source_box))
        output = BytesIO()
        cropped.save(output, format="PNG")
        return RenderedCrop(
            page_number=page_number,
            image_png=output.getvalue(),
            page_box=page_box,
            source_box=source_box,
            source_unit="image_pixels",
        )
