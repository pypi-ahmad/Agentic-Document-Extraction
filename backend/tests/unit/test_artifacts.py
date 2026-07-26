from io import BytesIO
from zipfile import ZipFile

import fitz
from PIL import Image

from app.services.parsing.artifacts import (
    build_bundle,
    build_grounding_pdf,
    build_searchable_pdf,
    build_verification_overlay,
    crop_region,
)
from app.services.parsing.contracts import BoundingBox, DocumentLayout, PageLayout, Region


def _blank_pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=200, height=300)
    value = document.tobytes()
    document.close()
    return value


def _layout() -> DocumentLayout:
    return DocumentLayout(
        pages=[
            PageLayout(
                page_number=1,
                width=200,
                height=300,
                regions=[
                    Region(
                        id="p0001-r0001",
                        type="text",
                        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.3),
                        content="Searchable region text",
                    ),
                    Region(
                        id="p0001-r0002",
                        type="table",
                        bbox=BoundingBox(left=0.1, top=0.4, right=0.9, bottom=0.7),
                        content="A | B",
                    ),
                ],
            )
        ]
    )


def test_grounding_pdf_contains_typed_labels_and_distinct_region_colors() -> None:
    output = build_grounding_pdf(_blank_pdf(), "source.pdf", _layout())
    document = fitz.open(stream=output, filetype="pdf")
    try:
        assert document.page_count == 1
        text = document[0].get_text()
        assert "p0001-r0001 · text" in text
        assert "p0001-r0002 · table" in text
        colors = {drawing["color"] for drawing in document[0].get_drawings()}
        assert len(colors) == 2
    finally:
        document.close()


def test_searchable_pdf_contains_invisible_region_text() -> None:
    output, warnings = build_searchable_pdf(_blank_pdf(), "source.pdf", _layout())
    document = fitz.open(stream=output, filetype="pdf")
    try:
        assert "Searchable region text" in document[0].get_text()
        assert warnings == []
    finally:
        document.close()


def test_crop_region_uses_normalized_coordinates() -> None:
    source = BytesIO()
    Image.new("RGB", (100, 80), "white").save(source, "PNG")

    cropped = crop_region(
        source.getvalue(), BoundingBox(left=0.1, top=0.25, right=0.6, bottom=0.75)
    )

    with Image.open(BytesIO(cropped)) as image:
        assert image.size == (50, 40)


def test_verification_overlay_draws_region_coordinates() -> None:
    source = BytesIO()
    Image.new("RGB", (100, 80), "white").save(source, "PNG")

    output = build_verification_overlay(source.getvalue(), _layout().pages[0].regions)

    with Image.open(BytesIO(output)) as image:
        assert image.size == (100, 80)
        assert image.getpixel((10, 8)) != (255, 255, 255)


def test_bundle_has_stable_sorted_paths() -> None:
    bundle = build_bundle({"document.md": b"hello", "source.pdf": b"pdf", "warnings.json": b"[]"})

    with ZipFile(BytesIO(bundle)) as archive:
        assert archive.namelist() == ["document.md", "source.pdf", "warnings.json"]
        assert archive.read("document.md") == b"hello"
