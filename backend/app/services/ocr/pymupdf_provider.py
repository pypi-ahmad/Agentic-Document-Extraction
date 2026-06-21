"""Built-in PDF text parser using PyMuPDF."""

from pathlib import Path

from app.services.ocr.base import (
    BaseOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProviderError,
    OCRResult,
)


class PyMuPDFProvider(BaseOCRProvider):
    """Extract text from PDF files via PyMuPDF.

    This is an internal PDF fallback/parser, not a full image OCR engine.
    """

    is_user_selectable = False
    supported_file_types = frozenset({"pdf"})

    @property
    def provider_id(self) -> str:
        return "pymupdf"

    @property
    def display_name(self) -> str:
        return "Built-in PDF reader (PyMuPDF)"

    async def extract_text(self, file_path: Path) -> OCRResult:
        import fitz  # pymupdf

        try:
            doc = fitz.open(str(file_path))
            pages: list[str] = []
            page_results: list[OCRPageResult] = []
            for idx, page in enumerate(doc):
                page_text = page.get_text()
                pages.append(page_text)

                # Extract text blocks with bounding boxes
                blocks: list[OCRBlock] = []
                for b in page.get_text("blocks"):
                    # b = (x0, y0, x1, y1, text, block_no, block_type)
                    if b[6] == 0:  # text block (not image)
                        blocks.append(
                            OCRBlock(
                                text=b[4].strip(),
                                bbox=(b[0], b[1], b[2], b[3]),
                            )
                        )

                page_results.append(
                    OCRPageResult(
                        page_index=idx,
                        text=page_text,
                        blocks=blocks,
                    )
                )
            doc.close()

            full_text = "\n\n".join(pages)
            return OCRResult(
                text=full_text,
                pages=pages,
                provider=self.provider_id,
                page_results=page_results,
            )
        except Exception as exc:
            raise OCRProviderError(self.provider_id, str(exc)) from exc

    def is_available(self) -> bool:
        try:
            import fitz  # noqa: F401

            return True
        except Exception:
            return False
