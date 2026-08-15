from io import BytesIO

import fitz
import pytest
from PIL import Image

from paperplane.ingest import (
    DocumentInputError,
    inspect_document,
    render_page,
    select_page_range,
    subset_pdf_pages,
)


def _pdf_bytes() -> bytes:
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((50, 80), "Native PDF text " * 5)
    value = document.tobytes()
    document.close()
    return value


def _image_bytes(fmt: str = "PNG", frames: int = 1) -> bytes:
    output = BytesIO()
    images = [Image.new("RGB", (100, 60), "white") for _ in range(frames)]
    if frames == 1:
        images[0].save(output, format=fmt)
    else:
        images[0].save(output, format=fmt, save_all=True, append_images=images[1:])
    return output.getvalue()


def test_inspect_pdf_reports_page_count_and_mime() -> None:
    inspected = inspect_document(_pdf_bytes(), "report.pdf", max_bytes=1_000_000, max_pages=10)

    assert inspected.mime_type == "application/pdf"
    assert inspected.page_count == 1
    assert inspected.source_format == "pdf"


def test_inspect_counts_mixed_pdf_without_automatic_routing() -> None:
    document = fitz.open()
    native = document.new_page(width=300, height=400)
    native.insert_text((50, 80), "Selectable native document text " * 3)
    document.new_page(width=300, height=400)
    data = document.tobytes()
    document.close()

    inspected = inspect_document(data, "mixed.pdf", max_bytes=1_000_000, max_pages=10)

    assert inspected.page_count == 2


def test_inspect_accepts_short_selectable_pdf_text() -> None:
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((50, 80), "Paid")
    data = document.tobytes()
    document.close()

    inspected = inspect_document(data, "stamp.pdf", max_bytes=1_000_000, max_pages=10)

    assert inspected.page_count == 1


def test_inspect_accepts_modern_office_input_for_local_conversion() -> None:
    inspected = inspect_document(b"conversion validates content", "report.docx", 1_000, 10)

    assert inspected.source_format == "docx"
    assert inspected.page_count == 1


def test_select_page_range_is_inclusive_and_defaults_to_last_page() -> None:
    assert select_page_range(5, 2, 4) == (2, 3, 4)
    assert select_page_range(5, 3, None) == (3, 4, 5)
    with pytest.raises(DocumentInputError, match="invalid_page_range"):
        select_page_range(5, 4, 3)
    with pytest.raises(DocumentInputError, match="invalid_page_range"):
        select_page_range(5, 1, 6)


def test_subset_pdf_pages_keeps_only_the_requested_source_pages() -> None:
    document = fitz.open()
    for page_number in range(1, 4):
        page = document.new_page(width=300, height=400)
        page.insert_text((50, 80), f"Source page {page_number}")
    data = document.tobytes()
    document.close()

    subset = subset_pdf_pages(data, 2, 3)

    preview = fitz.open(stream=subset, filetype="pdf")
    try:
        assert preview.page_count == 2
        assert [page.get_text().strip() for page in preview] == ["Source page 2", "Source page 3"]
    finally:
        preview.close()


def test_subset_pdf_pages_reuses_full_document_and_validates_range() -> None:
    data = _pdf_bytes()

    assert subset_pdf_pages(data, 1, 1) is data
    with pytest.raises(DocumentInputError, match="invalid_page_range"):
        subset_pdf_pages(data, 2, 2)


def test_inspect_rejects_oversized_or_unsupported_input() -> None:
    with pytest.raises(DocumentInputError, match="too_large"):
        inspect_document(_pdf_bytes(), "report.pdf", max_bytes=10, max_pages=10)
    with pytest.raises(DocumentInputError, match="unsupported_type"):
        inspect_document(b"hello", "note.txt", max_bytes=100, max_pages=10)


def test_inspect_rejects_pdf_canvas_that_would_exhaust_renderer() -> None:
    document = fitz.open()
    document.new_page(width=2500, height=2500)
    data = document.tobytes()
    document.close()

    with pytest.raises(DocumentInputError, match="canvas_too_large"):
        inspect_document(data, "oversized.pdf", max_bytes=1_000_000, max_pages=10)


def test_inspect_rejects_multiframe_image_over_total_pixel_budget(monkeypatch) -> None:
    data = _image_bytes("TIFF", frames=2)
    monkeypatch.setattr("paperplane.ingest.MAX_IMAGE_PIXELS", 10_000)

    with pytest.raises(DocumentInputError, match="image_too_large"):
        inspect_document(data, "oversized.tiff", max_bytes=1_000_000, max_pages=10)


def test_inspect_and_render_multiframe_tiff() -> None:
    data = _image_bytes("TIFF", frames=2)
    inspected = inspect_document(data, "scan.tiff", 1_000_000, 10)
    rendered = render_page(data, "scan.tiff", page_number=2, dpi=200)

    assert inspected.page_count == 2
    assert inspected.mime_type == "image/tiff"
    assert rendered.page_number == 2
    assert rendered.image_png.startswith(b"\x89PNG")


def test_render_pdf_page_extracts_normalized_native_words() -> None:
    rendered = render_page(_pdf_bytes(), "report.pdf", page_number=1, dpi=150)

    assert rendered.image_png.startswith(b"\x89PNG")
    assert rendered.width == 300
    assert rendered.height == 400
    assert "Native" in " ".join(word.text for word in rendered.native_words)
    assert all(0 <= word.bbox.left < word.bbox.right <= 1 for word in rendered.native_words)


def test_render_image_behaves_as_one_page_document() -> None:
    rendered = render_page(_image_bytes(), "scan.png", page_number=1, dpi=200)

    assert rendered.width == 100
    assert rendered.height == 60
    assert rendered.native_words == []


def test_inspect_and_render_webp() -> None:
    data = _image_bytes("WEBP")

    inspected = inspect_document(data, "scan.webp", 1_000_000, 10)
    rendered = render_page(data, "scan.webp", page_number=1, dpi=200)

    assert inspected.mime_type == "image/webp"
    assert rendered.image_png.startswith(b"\x89PNG")
