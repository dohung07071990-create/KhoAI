"""Request schemas for externally submitted security events."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class SecurityEventInput(BaseModel):
    camera: str = Field(default="external", max_length=40)
    people_in_zone: int = Field(default=0, ge=0)
    max_seconds: float = Field(default=0, ge=0)
    people: list[dict[str, Any]] = Field(default_factory=list)
    boxes: int = Field(default=0, ge=0)
    event_type: str | None = None
    severity: str = Field(default="warning", max_length=20)
    message: str | None = Field(default=None, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)
