"""Generate downloadable PDFs with auditable V2 region overlays."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image

from app.services.parsing.v2_contracts import GroundedChunk, VerificationStatus


def _source_pdf(source: bytes, filename: str) -> fitz.Document:
    if Path(filename).suffix.lower() == ".pdf":
        return fitz.open(stream=source, filetype="pdf")
    document = fitz.open()
    with Image.open(BytesIO(source)) as image:
        frame_count = int(getattr(image, "n_frames", 1))
        for frame in range(frame_count):
            image.seek(frame)
            rgb = image.convert("RGB")
            output = BytesIO()
            rgb.save(output, format="PNG")
            page = document.new_page(width=rgb.width, height=rgb.height)
            page.insert_image(page.rect, stream=output.getvalue())
    return document


def build_annotated_pdf(source: bytes, filename: str, chunks: list[GroundedChunk]) -> bytes:
    document = _source_pdf(source, filename)
    try:
        for chunk in chunks:
            if not chunk.grounding or chunk.page < 1 or chunk.page > document.page_count:
                continue
            page = document[chunk.page - 1]
            box = chunk.grounding[0].box
            rectangle = fitz.Rect(
                box.left * page.rect.width,
                box.top * page.rect.height,
                box.right * page.rect.width,
                box.bottom * page.rect.height,
            )
            color = (
                (0.0, 0.65, 0.35)
                if chunk.verification_status == VerificationStatus.VERIFIED
                else (0.9, 0.2, 0.15)
            )
            page.draw_rect(rectangle, color=color, width=1.2, overlay=True)
            page.insert_text(
                (rectangle.x0, max(8.0, rectangle.y0 - 2.0)),
                f"{chunk.order}. {chunk.id}",
                fontsize=6,
                color=color,
                overlay=True,
            )
        return document.tobytes(garbage=3, deflate=True)
    finally:
        document.close()
