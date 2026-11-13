"""Request schemas for card, RFID and access operations."""
from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

class CardCreate(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    name: str = Field(min_length=1, max_length=100)
    age: int | None = Field(default=None, ge=0, le=120)
    expires_at: str | None = Field(default=None, description="Ngày hết hạn YYYY-MM-DD")
    daily_quota: int = Field(default=3, ge=1, le=1000)
    color: str | None = Field(default=None, max_length=20)
    zones: list[str] = Field(default_factory=lambda: ["external_usb_zone"])
    item: str | None = Field(default=None, max_length=100)
    boxes: int = Field(default=0, ge=0, le=100000)

    @field_validator("expires_at")
    @classmethod
    def validate_expiry(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError):
            raise ValueError("expires_at phải đúng định dạng YYYY-MM-DD")

    @field_validator("color")
    @classmethod
    def validate_color(cls, value: str | None) -> str | None:
        if value in (None, ""):
            return None
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}|[A-Za-z]{1,20}", value):
            raise ValueError("color chỉ nhận mã hex #RRGGBB hoặc tên màu chữ")
        return value

class CardUpdate(BaseModel):
    active: bool

class RFIDScan(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    device_id: str = Field(default="esp32-door", max_length=100)

class DeviceHeartbeat(BaseModel):
    device_id: str = Field(default="esp32-door", max_length=100)

class AccessCheck(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    # [NEW] Optional track ID must be explicitly selected; RFID alone cannot identify a person in video.
    track_id: int | None = Field(default=None, ge=0)

class TrackAssociation(BaseModel):
    uid: str = Field(min_length=4, max_length=24)
    track_id: int = Field(ge=0)
