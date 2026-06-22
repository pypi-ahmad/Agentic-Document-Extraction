"""PaddleOCR-backed local OCR provider.

Supports both PaddleOCR 2.x (``ocr.ocr(...)`` API, ``list[list]``
return) and PaddleOCR 3.x (``ocr.predict(...)`` API, ``list[dict]``
return). The 3.x path is the recommended one going forward; the
2.x path is kept for users on legacy installs.

PaddleOCR 3.x API (>= 3.0.0):
    ocr = PaddleOCR(
        use_doc_orientation_classify=True,
        use_doc_unwarping=True,
        use_textline_orientation=True,
        lang="en",
    )
    results = ocr.predict("doc.png")
    # results is a list of per-page dicts:
    #   {"rec_texts": [...], "rec_scores": [...], "rec_polys": [...]}

PaddleOCR 2.x API (< 3.0.0):
    ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    results = ocr.ocr("doc.png", cls=True)
    # results is a list of per-page lists:
    #   [[[box_pts, (text, conf)], ...], ...]

Install
-------

- 3.x: ``pip install paddleocr>=3.7 paddlepaddle>=3.0`` (or the
  ``ade[paddleocr]`` extra).
- 2.x (legacy): install the 2.x line and set
  ``PADDLEOCR_USE_V2=1`` to force the legacy code path.

Requires the feature flag ``ENABLE_PADDLEOCR=true`` in ``.env``.
Not bundled in the default requirements.
"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

from app.models.enums import ParserEngine
from app.services.ocr.base import (
    BaseOCRProvider,
    OCRBlock,
    OCRPageResult,
    OCRProviderError,
    OCRResult,
)


def _paddleocr_version() -> tuple[int, int, int]:
    """Return the installed PaddleOCR version as a (major, minor, patch) tuple.

    Returns ``(0, 0, 0)`` if PaddleOCR is not importable.
    """
    try:
        from paddleocr import __version__  # type: ignore[import-untyped]

    except ImportError:
        return (0, 0, 0)
    parts = __version__.split(".")
    nums: list[int] = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return nums[0], nums[1], nums[2]


class PaddleOCRProvider(BaseOCRProvider):
    feature_flag_name = "enable_paddleocr"
    supported_file_types = frozenset({"png", "jpeg", "tiff"})

    @property
    def provider_id(self) -> str:
        return ParserEngine.PADDLEOCR.value

    @property
    def display_name(self) -> str:
        major, _, _ = _paddleocr_version()
        if major >= 3:
            return "PaddleOCR 3.x (local image OCR)"
        return "PaddleOCR 2.x (local image OCR)"

    async def extract_text(self, file_path: Path) -> OCRResult:
        if not self.is_available():
            raise OCRProviderError(
                self.provider_id,
                "paddleocr is not installed. Run: pip install paddleocr paddlepaddle",
            )
        # Pin to the 2.x path when the user explicitly asks for it
        # (e.g. on a legacy install that cannot upgrade paddlepaddle).
        force_v2 = os.environ.get("PADDLEOCR_USE_V2", "").lower() in ("1", "true", "yes")
        major, _, _ = _paddleocr_version()
        use_v3 = (major >= 3) and not force_v2

        try:
            if use_v3:
                return await self._extract_v3(file_path)
            return await self._extract_v2(file_path)
        except Exception as exc:
            raise OCRProviderError(self.provider_id, str(exc)) from exc

    # ── PaddleOCR 3.x ──────────────────────────────────────────────

    async def _extract_v3(self, file_path: Path) -> OCRResult:
        from paddleocr import PaddleOCR  # type: ignore[import-untyped]

        ocr = PaddleOCR(
            use_doc_orientation_classify=True,
            use_doc_unwarping=True,
            use_textline_orientation=True,
            lang="en",
        )
        result = ocr.predict(str(file_path))

        pages: list[str] = []
        page_results: list[OCRPageResult] = []
        all_confidences: list[float] = []

        for idx, page_result in enumerate(result):
            if not isinstance(page_result, dict):
                pages.append("")
                page_results.append(OCRPageResult(page_index=idx, text=""))
                continue
            texts: list[str] = list(page_result.get("rec_texts") or [])
            scores: list[float] = list(page_result.get("rec_scores") or [])
            polys = page_result.get("rec_polys") or []

            blocks: list[OCRBlock] = []
            lines: list[str] = []
            for i, text in enumerate(texts):
                if text is None or text == "":
                    continue
                try:
                    conf = float(scores[i]) if i < len(scores) else 0.0
                except (TypeError, ValueError):
                    conf = 0.0
                bbox: tuple[float, float, float, float] | None = None
                if i < len(polys):
                    poly = polys[i]
                    try:
                        xs = [float(p[0]) for p in poly]
                        ys = [float(p[1]) for p in poly]
                        bbox = (min(xs), min(ys), max(xs), max(ys))
                    except (TypeError, IndexError, ValueError):
                        bbox = None
                blocks.append(OCRBlock(text=str(text), bbox=bbox, confidence=conf))
                lines.append(str(text))
                all_confidences.append(conf)

            page_text = "\n".join(lines)
            pages.append(page_text)
            page_conf = (
                sum(b.confidence for b in blocks if b.confidence is not None)
                / max(1, sum(1 for b in blocks if b.confidence is not None))
                if any(b.confidence is not None for b in blocks)
                else None
            )
            page_results.append(
                OCRPageResult(
                    page_index=idx,
                    text=page_text,
                    blocks=blocks,
                    confidence=page_conf,
                )
            )

        doc_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else None
        return OCRResult(
            text="\n\n".join(pages),
            pages=pages,
            provider=self.provider_id,
            page_results=page_results,
            confidence=doc_confidence,
            raw={
                "engine": "paddleocr-3",
                "runtime": self.display_name,
                "page_count": len(result),
            },
        )

    # ── PaddleOCR 2.x (legacy) ─────────────────────────────────────

    async def _extract_v2(self, file_path: Path) -> OCRResult:
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
                try:
                    conf = float(line[1][1])
                except (TypeError, ValueError):
                    conf = 0.0
                bbox_pts = line[0]  # [[x0,y0],...]
                try:
                    x_coords = [float(p[0]) for p in bbox_pts]
                    y_coords = [float(p[1]) for p in bbox_pts]
                    bbox: tuple[float, float, float, float] | None = (
                        min(x_coords),
                        min(y_coords),
                        max(x_coords),
                        max(y_coords),
                    )
                except (TypeError, IndexError, ValueError):
                    bbox = None
                blocks.append(OCRBlock(text=str(text), bbox=bbox, confidence=conf))
                lines.append(str(text))
                all_confidences.append(conf)

            page_text = "\n".join(lines)
            pages.append(page_text)
            page_conf = (
                sum(b.confidence for b in blocks if b.confidence is not None)
                / max(1, sum(1 for b in blocks if b.confidence is not None))
                if any(b.confidence is not None for b in blocks)
                else None
            )
            page_results.append(
                OCRPageResult(
                    page_index=idx,
                    text=page_text,
                    blocks=blocks,
                    confidence=page_conf,
                )
            )

        doc_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else None
        return OCRResult(
            text="\n\n".join(pages),
            pages=pages,
            provider=self.provider_id,
            page_results=page_results,
            confidence=doc_confidence,
            raw={
                "engine": "paddleocr-2",
                "runtime": self.display_name,
                "paddle_raw_length": len(result),
            },
        )

    def is_available(self) -> bool:
        try:
            importlib.import_module("paddleocr")
            return True
        except Exception:
            return False
