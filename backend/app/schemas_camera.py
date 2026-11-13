"""Request schemas for camera zones and spatial calibration."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

class CameraZoneUpdate(BaseModel):
    points: list[list[float]] = Field(min_length=3, max_length=30)
    frame_size: list[int] | None = Field(default=None, min_length=2, max_length=2)

class CameraAntiTheftUpdate(BaseModel):
    enabled: bool

class HomographyCalibrationInput(BaseModel):
    image_points: list[list[float]] = Field(min_length=4, max_length=100)
    floor_points: list[list[float]] = Field(min_length=4, max_length=100)
    floor_units: str = Field(default="warehouse_units", min_length=1, max_length=32)
    max_rms_error: float = Field(default=0.15, gt=0, le=1000)

    @field_validator("image_points", "floor_points")
    @classmethod
    def validate_xy_pairs(cls, value: list[list[float]]) -> list[list[float]]:
        if any(len(point) != 2 for point in value):
            raise ValueError("Mỗi điểm phải có đúng hai tọa độ x, y.")
        return value

class RFIDEntryROIUpdate(BaseModel):
    points: list[list[float]] = Field(min_length=3, max_length=30)
