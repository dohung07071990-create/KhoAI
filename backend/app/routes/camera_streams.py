"""Compatibility facade composing the camera streaming route modules."""
from __future__ import annotations
from typing import Any
from fastapi import APIRouter
from .camera_usb_stream import create_usb_camera_stream_router
from .camera_webrtc import create_camera_webrtc_router
from .camera_stream_metadata import create_camera_stream_metadata_router
from .inside_camera_stream import create_inside_camera_stream_router


def create_camera_stream_router(services: Any) -> tuple[APIRouter, Any]:
    router = APIRouter()
    usb_router, camera_stream = create_usb_camera_stream_router(services)
    webrtc_router, camera_webrtc_offer = create_camera_webrtc_router(services)
    metadata_router, camera_streams_websocket = create_camera_stream_metadata_router(services)
    inside_router, inside_camera_stream = create_inside_camera_stream_router(services)
    router.include_router(usb_router)
    router.include_router(webrtc_router)
    router.include_router(metadata_router)
    router.include_router(inside_router)
    handlers = type("CameraStreamHandlers", (), {
        "camera_stream": staticmethod(camera_stream),
        "camera_webrtc_offer": staticmethod(camera_webrtc_offer),
        "camera_streams_websocket": staticmethod(camera_streams_websocket),
        "inside_camera_stream": staticmethod(inside_camera_stream),
    })
    return router, handlers
