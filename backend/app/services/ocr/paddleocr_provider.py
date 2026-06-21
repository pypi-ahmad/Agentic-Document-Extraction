"""PaddleOCR-backed local OCR provider.

Requires a separate install (``pip install paddleocr paddlepaddle``)
and the feature flag ``ENABLE_PADDLEOCR=true`` in ``.env``.
Not bundled in the default requirements.
"""

import importlib
from pathlib import Path

from app.models.enums import ParserEngine
from app.services.ocr.base import (
    BaseOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProviderError,
    OCRResult,
)


class PaddleOCRProvider(BaseOCRProvider):
    feature_flag_name = "enable_paddleocr"
    supported_file_types = frozenset({"png", "jpeg", "tiff"})

    @property
    def provider_id(self) -> str:
        return ParserEngine.PADDLEOCR.value

    @property
    def display_name(self) -> str:
        return "PaddleOCR (local image OCR)"

    async def extract_text(self, file_path: Path) -> OCRResult:
        if not self.is_available():
            raise OCRProviderError(
                self.provider_id,
                "paddleocr is not installed. Run: pip install paddleocr paddlepaddle",
            )
        try:
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            result = ocr.ocr(str(file_path), cls=True)

            pages: list[str] = []
            page_results: list[OCRPageResult] = []
            all_confidences: list[float] = []

            for idx, page_result in enumerate(result):
                if page_result is None:
                    pages.append("")
                    page_results.append(OCRPageResult(page_index=idx, text=""))
                    continue

                blocks: list[OCRBlock] = []
                lines: list[str] = []
                for line in page_result:
                    if not line or not line[1]:
                        continue
                    text = line[1][0]
                    conf = float(line[1][1])
                    bbox_pts = line[0]  # [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
                    x_coords = [p[0] for p in bbox_pts]
                    y_coords = [p[1] for p in bbox_pts]
                    blocks.append(
                        OCRBlock(
                            text=text,
                            bbox=(
                                min(x_coords),
                                min(y_coords),
                                max(x_coords),
                                max(y_coords),
                            ),
                            confidence=conf,
                        )
                    )
                    lines.append(text)
                    all_confidences.append(conf)

                page_text = "\n".join(lines)
                pages.append(page_text)
                confidences = [block.confidence for block in blocks if block.confidence is not None]
                page_conf = sum(confidences) / len(confidences) if confidences else None
                page_results.append(
                    OCRPageResult(
                        page_index=idx,
                        text=page_text,
                        blocks=blocks,
                        confidence=page_conf,
                    )
                )

            doc_confidence = (
                sum(all_confidences) / len(all_confidences) if all_confidences else None
            )

            return OCRResult(
                text="\n\n".join(pages),
                pages=pages,
                provider=self.provider_id,
                page_results=page_results,
                confidence=doc_confidence,
                raw={
                    "engine": "paddleocr",
                    "runtime": "PaddleOCR (local image OCR)",
                    "paddle_raw_length": len(result),
                },
            )
        except Exception as exc:
            raise OCRProviderError(self.provider_id, str(exc)) from exc

    def is_available(self) -> bool:
        try:
            importlib.import_module("paddleocr")
            return True
        except Exception:
            return False
