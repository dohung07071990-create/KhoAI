"""Camera protection and RFID-entry ROI configuration routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..schemas import CameraAntiTheftUpdate, CameraZoneUpdate, RFIDEntryROIUpdate


def create_camera_config_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.put("/api/camera/anti-theft", dependencies=[Depends(services.require_admin)])
    def update_camera_anti_theft(payload: CameraAntiTheftUpdate) -> dict[str, Any]:
        """Bật/tắt độc lập; khi bật, người đang ở trong vùng nguy hiểm được đánh giá ngay."""
        try:
            detector = services.detector_provider()
            detector.start()
            return {"ok": True, **detector.set_anti_theft(payload.enabled)}
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không thể thay đổi trạng thái chống trộm")
            raise HTTPException(status_code=503, detail="Không thể thay đổi trạng thái chống trộm lúc này.") from exc

    @router.get("/api/camera/zone", dependencies=[Depends(services.require_admin)])
    def get_camera_zone() -> dict[str, Any]:
        """Đọc vùng bảo vệ của riêng camera USB ngoài."""
        try:
            status = services.detector_provider().status()
            return {"points": status["zone_points"], "frame_size": status["zone_frame_size"],
                    "zone_mode": status["zone_mode"]}
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không đọc được vùng bảo vệ camera USB")
            raise HTTPException(status_code=503, detail="Không thể đọc vùng bảo vệ camera lúc này.") from exc

    @router.put("/api/camera/zone", dependencies=[Depends(services.require_admin)])
    def update_camera_zone(payload: CameraZoneUpdate) -> dict[str, Any]:
        """Lưu vùng bảo vệ chuẩn hóa (0–1) cho pipeline camera USB + YOLO."""
        try:
            detector = services.detector_provider()
            points = [(float(point[0]), float(point[1])) for point in payload.points if len(point) == 2]
            if len(points) != len(payload.points):
                raise ValueError("Mỗi điểm vùng phải có đúng hai tọa độ x, y.")
            services.validate_zone(points)
            current = detector.status().get("frame_size")
            requested_size = payload.frame_size or current
            frame_size = (int(requested_size[0]), int(requested_size[1])) if requested_size else None
            detector.set_zone(points, save=True, frame_size=frame_size)
            return {"ok": True, **get_camera_zone()}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không thể cập nhật vùng bảo vệ camera USB")
            raise HTTPException(status_code=503, detail="Không thể cập nhật vùng bảo vệ camera lúc này.") from exc

    @router.get("/api/rfid/entry-roi", dependencies=[Depends(services.require_admin)])
    def get_rfid_entry_roi() -> dict[str, Any]:
        try:
            detector = services.detector_provider()
            return {"points": [[x, y] for x, y in detector.rfid_entry_roi]}
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không đọc được ROI cửa RFID")
            raise HTTPException(status_code=503, detail="Không thể đọc cấu hình ROI cửa lúc này.") from exc

    @router.put("/api/rfid/entry-roi", dependencies=[Depends(services.require_admin)])
    def update_rfid_entry_roi(payload: RFIDEntryROIUpdate) -> dict[str, Any]:
        try:
            detector = services.detector_provider()
            if any(len(point) != 2 for point in payload.points):
                raise ValueError("Mỗi điểm ROI phải có đúng hai tọa độ x, y.")
            points = detector.set_rfid_entry_roi(payload.points)
            return {"ok": True, "points": [[x, y] for x, y in points]}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không thể lưu ROI cửa RFID")
            raise HTTPException(status_code=503, detail="Không thể lưu cấu hình ROI cửa lúc này.") from exc

    @router.get("/api/rfid/pending", dependencies=[Depends(services.require_admin)])
    def list_pending_rfid_bindings() -> dict[str, Any]:
        try:
            detector = services.detector_provider()
            detector.start()
            status = detector.status()
            return {"tickets": detector.pending_rfid_tickets(),
                    "tracks": [{"track_id": int(track_id),
                                "state": status.get("decision_tracks", {}).get(str(track_id), {}).get("state", "UNKNOWN"),
                                "thumbnail_url": f"/api/camera/tracks/{int(track_id)}/thumbnail"}
                               for track_id in status.get("tracked_person_ids", [])]}
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không đọc được danh sách RFID đang chờ ghép")
            raise HTTPException(status_code=503, detail="Không thể đọc danh sách ghép thẻ lúc này.") from exc

    return router
