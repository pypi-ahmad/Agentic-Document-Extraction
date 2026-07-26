"""Coordinate-aware local checks used before visual model review."""

from __future__ import annotations

from io import BytesIO
from typing import Any, cast

from PIL import Image, ImageStat

from app.services.parsing.agentic_contracts import (
    QualityStatus,
    VerificationMethod,
    VisualVerification,
)
from app.services.parsing.artifacts import crop_region
from app.services.parsing.contracts import Region


def verify_region_coordinates(
    image_png: bytes, regions: list[Region]
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for region in regions:
        if not region.id:
            continue
        reasons: list[str] = []
        status = QualityStatus.PASS
        crop = crop_region(image_png, region.bbox)
        with Image.open(BytesIO(crop)) as image:
            if image.width < 2 or image.height < 2:
                status = QualityStatus.FAIL
                reasons.append("coordinate_crop_too_small")
            elif region.type not in {"figure", "chart"}:
                grayscale = image.convert("L")
                extrema = cast(tuple[int, int], grayscale.getextrema())
                mean = ImageStat.Stat(grayscale).mean[0]
                if extrema[1] - extrema[0] < 3 and mean > 245:
                    status = QualityStatus.WARN
                    reasons.append("coordinate_crop_appears_blank")
        if not region.content.strip():
            status = QualityStatus.FAIL
            reasons.append("coordinate_region_has_no_text")
        if region.recognition_candidates and not any(
            candidate.selected for candidate in region.recognition_candidates
        ):
            if status == QualityStatus.PASS:
                status = QualityStatus.WARN
            reasons.append("selected_candidate_provenance_missing")
        if not reasons:
            reasons.append("content_is_grounded_to_region_crop")
        results[region.id] = VisualVerification(
            region_id=region.id,
            bbox=region.bbox,
            status=status,
            methods=[VerificationMethod.LOCAL_COORDINATE],
            reasons=reasons,
        ).model_dump(mode="json")
    return results
