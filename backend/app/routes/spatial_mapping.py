"""Spatial mapping calibration endpoints for the external USB camera."""
from __future__ import annotations

import logging
from typing import Any, Protocol

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import HomographyCalibrationInput


class SpatialMappingServices(Protocol):
    require_admin: Any
    detector_provider: Any
    logger: logging.Logger


def create_spatial_mapping_router(services: SpatialMappingServices) -> APIRouter:
    router = APIRouter()

    @router.get("/api/camera/spatial-mapping", dependencies=[Depends(services.require_admin)])
    def get_spatial_mapping() -> dict[str, Any]:
        """Return the USB camera floor-calibration state and mapped tracks."""
        try:
            state = services.detector_provider().status()
            return {
                "mapping": state.get("spatial_mapping", {"enabled": False, "valid": False}),
                "frame_size": state.get("frame_size"),
                "tracks": list(state.get("spatial_tracks", {}).values()),
            }
        except Exception as exc:  # noqa: BLE001 - convert detector failures to API errors
            services.logger.exception("Không đọc được cấu hình Spatial Mapping")
            raise HTTPException(
                status_code=503, detail="Không thể đọc cấu hình Spatial Mapping lúc này."
            ) from exc

    @router.put("/api/camera/spatial-mapping", dependencies=[Depends(services.require_admin)])
    def calibrate_spatial_mapping(payload: HomographyCalibrationInput) -> dict[str, Any]:
        """Calibrate pixel-to-floor mapping using the active camera frame size."""
        try:
            from ai.homography import HomographyCalibrationError
        except ImportError as exc:
            services.logger.exception("Không tải được module Homography")
            raise HTTPException(
                status_code=503, detail="Tính năng hiệu chuẩn không khả dụng trong môi trường này."
            ) from exc
        try:
            detector = services.detector_provider()
            state = detector.status()
            frame_size = state.get("frame_size")
            if not state.get("camera_ok") or not frame_size:
                raise HTTPException(
                    status_code=409,
                    detail="Camera USB chưa hoạt động; không thể lấy kích thước khung hình hiệu chuẩn.",
                )
            result = detector._homography.calibrate(
                payload.image_points,
                payload.floor_points,
                frame_size,
                floor_units=payload.floor_units,
                max_rms_error=payload.max_rms_error,
            )
            return {"ok": True, "mapping": result, "frame_size": frame_size}
        except HomographyCalibrationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không thể hiệu chuẩn Spatial Mapping")
            raise HTTPException(
                status_code=503, detail="Không thể hiệu chuẩn Spatial Mapping lúc này."
            ) from exc

    @router.delete("/api/camera/spatial-mapping", dependencies=[Depends(services.require_admin)])
    def invalidate_spatial_mapping() -> dict[str, Any]:
        """Invalidate calibration after the camera has moved."""
        try:
            detector = services.detector_provider()
            return {
                "ok": True,
                "mapping": detector._homography.invalidate("operator_invalidated_camera_moved"),
            }
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không thể vô hiệu hóa Spatial Mapping")
            raise HTTPException(
                status_code=503, detail="Không thể vô hiệu hóa Spatial Mapping lúc này."
            ) from exc

    return router
