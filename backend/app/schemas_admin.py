"""Request schemas for administrator authentication and user management."""
from __future__ import annotations

from pydantic import BaseModel, Field

class AdminLogin(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=12, max_length=256)
    role: str = Field(default="admin", pattern="^(admin|viewer)$")

class AdminUserUpdate(BaseModel):
    active: bool | None = None
    role: str | None = Field(default=None, pattern="^(admin|viewer)$")
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    password: str | None = Field(default=None, min_length=12, max_length=256)
