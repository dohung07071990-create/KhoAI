"""Compatibility facade composing camera frame and evidence routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from .camera_evidence import create_camera_evidence_router
from .camera_frames import create_camera_frame_router


def create_camera_media_router(services: Any) -> APIRouter:
    router = APIRouter()
    router.include_router(create_camera_frame_router(services))
    router.include_router(create_camera_evidence_router(services))
    return router
