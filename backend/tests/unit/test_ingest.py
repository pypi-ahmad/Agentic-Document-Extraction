from io import BytesIO

import fitz
import pytest
from PIL import Image

from app.services.parsing.ingest import DocumentInputError, inspect_document, render_page


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


def test_inspect_rejects_oversized_or_unsupported_input() -> None:
    with pytest.raises(DocumentInputError, match="too_large"):
        inspect_document(_pdf_bytes(), "report.pdf", max_bytes=10, max_pages=10)
    with pytest.raises(DocumentInputError, match="unsupported_type"):
        inspect_document(b"hello", "note.txt", max_bytes=100, max_pages=10)


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
