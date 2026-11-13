"""Compatibility facade composing camera-event feed and incident timeline routes."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter

from .camera_event_feed import create_camera_event_feed_router
from .incident_timeline import create_incident_timeline_router


def create_camera_event_router(services: Any) -> APIRouter:
    router = APIRouter()
    router.include_router(create_camera_event_feed_router(services))
    router.include_router(create_incident_timeline_router(services))
    return router
