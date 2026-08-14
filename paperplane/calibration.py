"""Version- and corpus-pinned confidence calibration."""

from __future__ import annotations

from itertools import pairwise

from pydantic import BaseModel, Field


class CalibrationProfile(BaseModel):
    engine: str
    model: str
    version: str
    corpus_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    breakpoints: list[tuple[float, float]]

    def calibrate(self, raw: float) -> float:
        score = min(1.0, max(0.0, raw))
        points = sorted(self.breakpoints)
        if not points:
            return score
        if score <= points[0][0]:
            return points[0][1]
        for (x0, y0), (x1, y1) in pairwise(points):
            if score <= x1:
                fraction = (score - x0) / (x1 - x0) if x1 != x0 else 0
                return min(1.0, max(0.0, y0 + fraction * (y1 - y0)))
        return points[-1][1]


class ConfidenceResult(BaseModel):
    raw: float = Field(ge=0, le=1)
    calibrated: float | None = Field(default=None, ge=0, le=1)
    label: str


def confidence_for(
    raw: float,
    *,
    engine: str,
    model: str,
    version: str,
    profile: CalibrationProfile | None,
) -> ConfidenceResult:
    if profile is None or (profile.engine, profile.model, profile.version) != (
        engine,
        model,
        version,
    ):
        return ConfidenceResult(raw=raw, calibrated=None, label="raw (uncalibrated)")
    return ConfidenceResult(raw=raw, calibrated=profile.calibrate(raw), label="calibrated")


__all__ = ["CalibrationProfile", "ConfidenceResult", "confidence_for"]
