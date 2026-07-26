from io import BytesIO

import fitz
from PIL import Image

from app.services.parsing.contracts import BoundingBox, NativeWord
from app.services.parsing.v2_grounding import (
    align_text_to_native_words,
    map_crop_box_to_page,
    render_crop,
)


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=200, height=300)
    page.insert_text((20, 50), "Invoice Number INV-42")
    result = document.tobytes()
    document.close()
    return result


def test_native_text_alignment_returns_exact_union_box() -> None:
    words = [
        NativeWord(text="Invoice", bbox=BoundingBox(left=0.1, top=0.1, right=0.2, bottom=0.2)),
        NativeWord(text="Number", bbox=BoundingBox(left=0.21, top=0.1, right=0.3, bottom=0.2)),
        NativeWord(text="INV-42", bbox=BoundingBox(left=0.31, top=0.1, right=0.42, bottom=0.2)),
    ]

    box = align_text_to_native_words("Invoice Number INV-42", words)

    assert box == BoundingBox(left=0.1, top=0.1, right=0.42, bottom=0.2)


def test_crop_relative_box_maps_back_to_page_coordinates() -> None:
    crop = BoundingBox(left=0.2, top=0.25, right=0.8, bottom=0.75)
    relative = BoundingBox(left=0.25, top=0.2, right=0.75, bottom=0.8)

    mapped = map_crop_box_to_page(crop, relative)

    assert mapped == BoundingBox(left=0.35, top=0.35, right=0.65, bottom=0.65)


def test_render_crop_preserves_pdf_coordinate_audit_trail() -> None:
    crop = render_crop(
        _pdf_bytes(),
        "invoice.pdf",
        page_number=1,
        box=BoundingBox(left=0.05, top=0.1, right=0.6, bottom=0.3),
        dpi=300,
        padding=0.05,
    )

    image = Image.open(BytesIO(crop.image_png))
    assert image.width > 400
    assert crop.source_unit == "pdf_points"
    assert crop.source_box == (0.0, 15.0, 130.0, 105.0)
    assert crop.page_box == BoundingBox(left=0, top=0.05, right=0.65, bottom=0.35)
