"""Authenticated read-only USB camera frame and visualization routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response


def create_camera_frame_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/camera/streams/status", dependencies=[Depends(services.require_admin_query)])
    def camera_streams_status() -> dict[str, Any]:
        """Viewer counts and distribution statistics; not capture/AI health."""
        return services.stream_manager_provider().snapshot()

    @router.get("/api/camera/tracks/{track_id}/thumbnail", dependencies=[Depends(services.require_admin_query)])
    def camera_track_thumbnail(track_id: int) -> Response:
        try:
            jpeg = services.detector_provider().track_thumbnail_jpeg(track_id)
            if jpeg is None:
                raise HTTPException(status_code=404, detail="Track không còn hiển thị hoặc ảnh không khả dụng.")
            return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:
            services.logger.exception("Không tạo được thumbnail Track %s", track_id)
            raise HTTPException(status_code=503, detail="Không thể tạo ảnh Track lúc này.") from exc

    @router.get("/api/camera/heatmap", dependencies=[Depends(services.require_admin_query)])
    def camera_heatmap(request: Request) -> Response:
        """Heatmap image derived only from the external USB camera."""
        try:
            detector = services.detector_provider()
            services.ensure_camera_for_read(request, detector)
            jpeg = detector.heatmap_jpeg()
            if jpeg is None:
                raise HTTPException(status_code=503, detail="Camera chưa có khung hình; hãy chờ vài giây.")
            return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không tạo được heatmap camera USB")
            raise HTTPException(status_code=503, detail="Không thể tạo heatmap camera lúc này.") from exc

    @router.get("/api/camera/snapshot", dependencies=[Depends(services.require_admin_query)])
    def camera_snapshot(request: Request) -> Response:
        """Latest raw USB webcam JPEG, without AI overlays."""
        try:
            detector = services.detector_provider()
            services.ensure_camera_for_read(request, detector)
            jpeg = detector.snapshot_jpeg(annotated=False)
            if jpeg is None:
                raise HTTPException(status_code=503, detail="Camera chưa có khung hình; hãy chờ vài giây.")
            return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không chụp được ảnh camera USB")
            raise HTTPException(status_code=503, detail="Không thể chụp ảnh camera lúc này.") from exc

    return router
