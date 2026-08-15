"""Document validation, inspection, rendering, and native word extraction."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import fitz
from PIL import Image, UnidentifiedImageError

from paperplane.types import BoundingBox, NativeWord

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
OFFICE_EXTENSIONS = {".docx", ".pptx", ".xlsx", ".odt", ".odp", ".ods", ".csv"}
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
    source_format: str
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
            oversized_pages: list[int] = []
            for index, page in enumerate(document, start=1):
                if page.rect.width * page.rect.height > MAX_PDF_CANVAS_AREA:
                    oversized_pages.append(index)
            if oversized_pages:
                raise DocumentInputError(
                    "canvas_too_large",
                    f"PDF page {oversized_pages[0]} exceeds the render canvas limit",
                )
        finally:
            document.close()
        if page_count > max_pages:
            raise DocumentInputError("too_many_pages", f"Document exceeds {max_pages} pages")
        return InspectedDocument(
            mime_type="application/pdf",
            page_count=page_count,
            source_format="pdf",
        )
    if suffix in OFFICE_EXTENSIONS:
        return InspectedDocument(
            mime_type=_office_mime_type(suffix),
            page_count=1,
            source_format=suffix.lstrip("."),
        )
    if suffix not in IMAGE_EXTENSIONS:
        raise DocumentInputError(
            "unsupported_type",
            "Supported types are PDF, PNG, JPEG, WebP, TIFF, BMP, DOCX, PPTX, XLSX, "
            "ODT, ODP, ODS, and CSV",
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
    return InspectedDocument(
        mime_type=mime,
        page_count=page_count,
        source_format=suffix.lstrip("."),
    )


def select_page_range(page_count: int, start: int = 1, end: int | None = None) -> tuple[int, ...]:
    """Validate an inclusive one-based range and return its page numbers."""

    selected_end = page_count if end is None else end
    if start < 1 or selected_end < 1 or start > selected_end:
        raise DocumentInputError("invalid_page_range", "Page range must be ordered and one-based")
    if selected_end > page_count:
        raise DocumentInputError(
            "invalid_page_range", f"Page range exceeds the document's {page_count} pages"
        )
    return tuple(range(start, selected_end + 1))


def subset_pdf_pages(data: bytes, start: int = 1, end: int | None = None) -> bytes:
    """Return PDF bytes containing only an inclusive one-based page range."""

    document = fitz.open(stream=data, filetype="pdf")
    try:
        selected_pages = select_page_range(document.page_count, start, end)
        if len(selected_pages) == document.page_count:
            return data
        document.select([page_number - 1 for page_number in selected_pages])
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()


def _office_mime_type(suffix: str) -> str:
    return {
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".odt": "application/vnd.oasis.opendocument.text",
        ".odp": "application/vnd.oasis.opendocument.presentation",
        ".ods": "application/vnd.oasis.opendocument.spreadsheet",
        ".csv": "text/csv",
    }[suffix]


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


def extract_native_words(data: bytes, filename: str, page_number: int) -> list[NativeWord]:
    """Extract observed native PDF words without rendering the page."""

    if Path(filename).suffix.lower() != ".pdf":
        return []
    document = fitz.open(stream=data, filetype="pdf")
    try:
        if page_number < 1 or page_number > document.page_count:
            raise DocumentInputError("invalid_page", "Page is outside the document")
        page = document[page_number - 1]
        width, height = float(page.rect.width), float(page.rect.height)
        return [
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
    finally:
        document.close()


@lru_cache(maxsize=1)
def _rapid_ocr():
    from rapidocr import RapidOCR

    return RapidOCR()


def extract_ocr_words(image_png: bytes) -> list[tuple[NativeWord, float]]:
    """Run local OCR and return only word boxes produced by the OCR engine."""

    result = _rapid_ocr()(image_png, return_word_box=True)
    if result.img is None or not result.word_results:
        return []
    height, width = result.img.shape[:2]
    words: list[tuple[NativeWord, float]] = []
    for line in result.word_results:
        if not isinstance(line, (list, tuple)):
            continue
        for item in line:
            if not isinstance(item, (list, tuple)) or len(item) != 3:
                continue
            text, confidence, points = item
            if not text or not points:
                continue
            if not all(isinstance(point, (list, tuple)) and len(point) >= 2 for point in points):
                continue
            point_values = cast(list[list[Any]], points)
            xs = [float(point[0]) for point in point_values]
            ys = [float(point[1]) for point in point_values]
            left, right = max(0.0, min(xs) / width), min(1.0, max(xs) / width)
            top, bottom = max(0.0, min(ys) / height), min(1.0, max(ys) / height)
            if right <= left or bottom <= top:
                continue
            words.append(
                (
                    NativeWord(
                        text=str(text),
                        bbox=BoundingBox(left=left, top=top, right=right, bottom=bottom),
                    ),
                    min(1.0, max(0.0, float(confidence))),
                )
            )
    return words
