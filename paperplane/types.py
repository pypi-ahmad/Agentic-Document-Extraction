"""Normalized document geometry used by the parsing pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    left: float = Field(ge=0, le=1)
    top: float = Field(ge=0, le=1)
    right: float = Field(ge=0, le=1)
    bottom: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_edges(self) -> BoundingBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("bounding box right/bottom must exceed left/top")
        return self


class NativeWord(BaseModel):
    text: str
    bbox: BoundingBox


__all__ = ["BoundingBox", "NativeWord"]
