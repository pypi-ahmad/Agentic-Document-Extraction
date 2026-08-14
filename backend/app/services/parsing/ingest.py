"""Document validation, inspection, rendering, and native word extraction."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, UnidentifiedImageError

from app.services.parsing.contracts import BoundingBox, NativeWord

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
MAX_PDF_CANVAS_AREA = 4_000_000
MAX_IMAGE_PIXELS = 40_000_000


class DocumentInputError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True)
class InspectedDocument:
    mime_type: str
    page_count: int
    findings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    image_png: bytes
    width: float
    height: float
    native_words: list[NativeWord]


def inspect_document(
    data: bytes, filename: str, max_bytes: int, max_pages: int
) -> InspectedDocument:
    if len(data) > max_bytes:
        raise DocumentInputError("too_large", f"Document exceeds the {max_bytes}-byte limit")
    suffix = Path(filename).suffix.lower()
    if suffix in PDF_EXTENSIONS:
        try:
            document = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise DocumentInputError("invalid_pdf", "PDF could not be opened") from exc
        try:
            if document.needs_pass:
                raise DocumentInputError("encrypted_pdf", "Encrypted PDFs are not supported")
            page_count = document.page_count
            if page_count < 1:
                raise DocumentInputError("empty_document", "Document contains no pages")
            oversized_pages = [
                index + 1
                for index, page in enumerate(document)
                if page.rect.width * page.rect.height > MAX_PDF_CANVAS_AREA
            ]
            if oversized_pages:
                raise DocumentInputError(
                    "canvas_too_large",
                    f"PDF page {oversized_pages[0]} exceeds the render canvas limit",
                )
        finally:
            document.close()
        if page_count > max_pages:
            raise DocumentInputError("too_many_pages", f"Document exceeds {max_pages} pages")
        return InspectedDocument(mime_type="application/pdf", page_count=page_count)
    if suffix not in IMAGE_EXTENSIONS:
        raise DocumentInputError(
            "unsupported_type", "Supported types are PDF, PNG, JPEG, WebP, and TIFF"
        )
    try:
        with Image.open(BytesIO(data)) as image:
            page_count = int(getattr(image, "n_frames", 1))
            if page_count > max_pages:
                raise DocumentInputError("too_many_pages", f"Document exceeds {max_pages} pages")
            total_pixels = 0
            for frame_index in range(page_count):
                image.seek(frame_index)
                total_pixels += image.width * image.height
                if total_pixels > MAX_IMAGE_PIXELS:
                    raise DocumentInputError(
                        "image_too_large", "Decoded image frames exceed the pixel limit"
                    )
            image.verify()
    except DocumentInputError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise DocumentInputError("invalid_image", "Image could not be opened") from exc
    mime = "image/jpeg" if suffix in {".jpg", ".jpeg"} else f"image/{suffix.lstrip('.')}"
    if suffix in {".tif", ".tiff"}:
        mime = "image/tiff"
    return InspectedDocument(mime_type=mime, page_count=page_count)


def render_page(data: bytes, filename: str, page_number: int, dpi: int) -> RenderedPage:
    suffix = Path(filename).suffix.lower()
    if page_number < 1:
        raise DocumentInputError("invalid_page", "Page numbers are one-based")
    if suffix == ".pdf":
        document = fitz.open(stream=data, filetype="pdf")
        try:
            if page_number > document.page_count:
                raise DocumentInputError("invalid_page", "Page is outside the document")
            page = document[page_number - 1]
            width, height = float(page.rect.width), float(page.rect.height)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
            image_png = pixmap.tobytes("png")
            native_words = [
                NativeWord(
                    text=str(item[4]),
                    bbox=BoundingBox(
                        left=max(0, min(float(item[0]) / width, 1)),
                        top=max(0, min(float(item[1]) / height, 1)),
                        right=max(0, min(float(item[2]) / width, 1)),
                        bottom=max(0, min(float(item[3]) / height, 1)),
                    ),
                )
                for item in page.get_text("words", sort=True)
                if item[4].strip() and item[2] > item[0] and item[3] > item[1]
            ]
            return RenderedPage(page_number, image_png, width, height, native_words)
        finally:
            document.close()
    with Image.open(BytesIO(data)) as image:
        frame_count = int(getattr(image, "n_frames", 1))
        if page_number > frame_count:
            raise DocumentInputError("invalid_page", "Page is outside the image")
        image.seek(page_number - 1)
        rgb = image.convert("RGB")
        output = BytesIO()
        rgb.save(output, format="PNG")
        return RenderedPage(page_number, output.getvalue(), float(rgb.width), float(rgb.height), [])
