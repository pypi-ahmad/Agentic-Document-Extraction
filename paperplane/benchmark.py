"""Reproducible benchmark manifests and transparent metric helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, Field


class BenchmarkDocument(BaseModel):
    id: str
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license: str
    tags: list[str] = Field(default_factory=list)


class BenchmarkManifest(BaseModel):
    version: str
    documents: list[BenchmarkDocument]
    engines: list[str]
    metrics: list[str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def character_accuracy(reference: str, candidate: str) -> float:
    """Normalized character accuracy based on Levenshtein edit distance."""

    if not reference:
        return 1.0 if not candidate else 0.0
    previous = list(range(len(candidate) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, actual in enumerate(candidate, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected != actual),
                )
            )
        previous = current
    return max(0.0, 1 - previous[-1] / len(reference))


def expected_calibration_error(
    confidences: list[float], outcomes: list[bool], *, bins: int = 10
) -> float:
    if len(confidences) != len(outcomes):
        raise ValueError("Confidence and outcome counts must match")
    if not confidences:
        return 0.0
    error = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        members = [
            item
            for item, confidence in enumerate(confidences)
            if lower <= confidence <= upper and (index == bins - 1 or confidence < upper)
        ]
        if not members:
            continue
        mean_confidence = sum(confidences[item] for item in members) / len(members)
        accuracy = sum(outcomes[item] for item in members) / len(members)
        error += len(members) / len(confidences) * abs(mean_confidence - accuracy)
    return error


__all__ = [
    "BenchmarkDocument",
    "BenchmarkManifest",
    "character_accuracy",
    "expected_calibration_error",
    "sha256_file",
]
