"""Generate grounded PDFs, searchable PDFs, region crops, and bundles."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import fitz
from PIL import Image, ImageDraw

from app.services.parsing.contracts import BoundingBox, DocumentLayout, Region

REGION_COLORS: dict[str, tuple[float, float, float]] = {
    "title": (0.47, 0.18, 0.78),
    "heading": (0.18, 0.38, 0.82),
    "text": (0.08, 0.45, 0.95),
    "list": (0.0, 0.55, 0.48),
    "table": (0.88, 0.38, 0.08),
    "chart": (0.78, 0.18, 0.48),
    "formula": (0.55, 0.25, 0.72),
    "figure": (0.72, 0.2, 0.22),
    "header": (0.42, 0.47, 0.55),
    "footer": (0.42, 0.47, 0.55),
    "page_number": (0.42, 0.47, 0.55),
    "code": (0.16, 0.55, 0.22),
    "quote": (0.58, 0.42, 0.12),
}


def _source_as_pdf(source: bytes, filename: str) -> fitz.Document:
    if Path(filename).suffix.lower() == ".pdf":
        return fitz.open(stream=source, filetype="pdf")
    with Image.open(BytesIO(source)) as image:
        rgb = image.convert("RGB")
        encoded = BytesIO()
        rgb.save(encoded, format="PNG")
        document = fitz.open()
        page = document.new_page(width=rgb.width, height=rgb.height)
        page.insert_image(page.rect, stream=encoded.getvalue())
        return document


def _selected_pdf(source: bytes, filename: str, layout: DocumentLayout) -> fitz.Document:
    original = _source_as_pdf(source, filename)
    selected = fitz.open()
    try:
        for page_layout in layout.pages:
            selected.insert_pdf(
                original, from_page=page_layout.page_number - 1, to_page=page_layout.page_number - 1
            )
    finally:
        original.close()
    return selected


def _rect(page: fitz.Page, bbox: BoundingBox) -> fitz.Rect:
    return fitz.Rect(
        bbox.left * page.rect.width,
        bbox.top * page.rect.height,
        bbox.right * page.rect.width,
        bbox.bottom * page.rect.height,
    )


def build_grounding_pdf(source: bytes, filename: str, layout: DocumentLayout) -> bytes:
    document = _selected_pdf(source, filename, layout)
    try:
        for output_index, page_layout in enumerate(layout.pages):
            page = document[output_index]
            for region in page_layout.regions:
                rectangle = _rect(page, region.bbox)
                color = REGION_COLORS.get(region.type, (0.08, 0.45, 0.95))
                page.draw_rect(rectangle, color=color, width=1, overlay=True)
                label_y = min(rectangle.y0 + 8, page.rect.height - 2)
                page.insert_text(
                    (rectangle.x0 + 2, label_y),
                    (
                        f"{(region.order if region.order is not None else '?')} · "
                        f"{region.id or 'region'} · {region.type} · "
                        f"{region.source_label or region.source} · "
                        f"{region.confidence:.0%}"
                        if region.confidence is not None
                        else f"{(region.order if region.order is not None else '?')} · "
                        f"{region.id or 'region'} · {region.type} · "
                        f"{region.source_label or region.source}"
                    ),
                    fontsize=6,
                    color=color,
                    overlay=True,
                )
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()


def build_searchable_pdf(
    source: bytes, filename: str, layout: DocumentLayout
) -> tuple[bytes, list[str]]:
    document = _selected_pdf(source, filename, layout)
    warnings: list[str] = []
    try:
        for output_index, page_layout in enumerate(layout.pages):
            page = document[output_index]
            for region in page_layout.regions:
                text = region.content.strip()
                if not text:
                    continue
                result = page.insert_textbox(
                    _rect(page, region.bbox),
                    text,
                    fontsize=6,
                    render_mode=3,
                    overlay=True,
                )
                if result < 0:
                    warnings.append(f"{region.id}: searchable text did not fit its region")
        return document.tobytes(garbage=3, deflate=True), warnings
    finally:
        document.close()


def crop_region(image_png: bytes, bbox: BoundingBox) -> bytes:
    with Image.open(BytesIO(image_png)) as image:
        left = round(bbox.left * image.width)
        top = round(bbox.top * image.height)
        right = round(bbox.right * image.width)
        bottom = round(bbox.bottom * image.height)
        crop = image.crop((left, top, right, bottom))
        output = BytesIO()
        crop.save(output, format="PNG")
        return output.getvalue()


def build_verification_overlay(image_png: bytes, regions: list[Region]) -> bytes:
    """Draw exact region coordinates and IDs on a page image for visual verification."""
    with Image.open(BytesIO(image_png)) as source:
        image = source.convert("RGB")
    draw = ImageDraw.Draw(image)
    for region in regions:
        box = region.bbox
        coordinates = (
            round(box.left * image.width),
            round(box.top * image.height),
            round(box.right * image.width),
            round(box.bottom * image.height),
        )
        rgb = tuple(round(channel * 255) for channel in REGION_COLORS[region.type])
        draw.rectangle(coordinates, outline=rgb, width=2)
        draw.text(
            (coordinates[0] + 2, coordinates[1] + 2),
            f"{region.id or 'region'} · {region.type}",
            fill=rgb,
            stroke_width=1,
            stroke_fill=(255, 255, 255),
        )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def build_bundle(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with ZipFile(output, mode="w") as archive:
        for name in sorted(files):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, files[name])
    return output.getvalue()
