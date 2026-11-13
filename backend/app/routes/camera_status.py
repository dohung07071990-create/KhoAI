"""Read-only health and camera/AI status routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException


def create_camera_status_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    def health() -> dict[str, Any]:
        result: dict[str, Any] = {"status": "ok", "service": "kho-ai-demo", "version": services.app_version}
        try:
            state = services.detector_provider().status()
            result.update({"camera_ok": bool(state.get("camera_ok")), "ai_ok": bool(state.get("ai_ok")),
                           "tracking_enabled": bool(state.get("tracking_enabled"))})
            if not result["camera_ok"] or not result["ai_ok"]:
                result["status"] = "degraded"
        except Exception:
            result.update({"camera_ok": False, "ai_ok": False, "tracking_enabled": False, "status": "degraded"})
        return result

    @router.get("/api/camera/status", dependencies=[Depends(services.require_session)])
    def camera_status() -> dict[str, Any]:
        """Tình trạng camera USB và pipeline YOLO/ByteTrack."""
        try:
            return services.augment_detector_status(services.detector_provider().status())
        except Exception as exc:  # noqa: BLE001
            services.logger.exception("Không đọc được trạng thái camera AI")
            raise HTTPException(status_code=503, detail="Không thể đọc trạng thái camera lúc này.") from exc

    @router.get("/api/cameras/center", dependencies=[Depends(services.require_session)])
    def camera_control_center() -> dict[str, Any]:
        import os

        stamp = services.now_business()
        result: dict[str, Any] = {
            "checked_at": stamp,
            "external": {"name": "Camera ngoài – USB/Iriun", "connected": False, "ai_enabled": True,
                         "tracker": "ByteTrack", "fps": None, "last_frame_at": None,
                         "error": "Chưa đọc được trạng thái camera."},
            "internal": {"name": "Camera trong – ESP32-CAM", "connected": False, "ai_enabled": False,
                         "fps": None, "last_frame_at": None,
                         "error": "Chưa có telemetry FPS từ ESP32-CAM."},
        }
        try:
            state = services.detector_provider().status()
            result["external"].update({
                "connected": bool(state.get("camera_ok")), "ai_ok": bool(state.get("ai_ok")),
                "fps": state.get("capture_fps"), "process_fps": state.get("process_fps"),
                "last_frame_age_ms": state.get("frame_age_ms"),
                "error": state.get("camera_error") or state.get("ai_error") or None,
            })
        except Exception as exc:
            services.logger.warning("Không đọc được trạng thái camera ngoài", exc_info=True)
            result["external"]["error"] = "Không thể đọc trạng thái camera ngoài lúc này."
        inside_url = os.getenv("KHOAI_ESP32_CAM_STREAM_URL", "").strip()
        result["internal"].update({
            "configured": bool(inside_url),
            "error": "Đã cấu hình stream; chưa có phép đo kết nối/FPS độc lập." if inside_url
                     else "Chưa cấu hình KHOAI_ESP32_CAM_STREAM_URL.",
        })
        return result

    @router.get("/api/ai/explainability", dependencies=[Depends(services.require_session)])
    def ai_explainability() -> dict[str, Any]:
        """Expose current decision inputs/reasons only when provided by the live detector."""
        try:
            state = services.detector_provider().status()
        except Exception as exc:
            services.logger.warning("Không đọc được trạng thái detector cho explainability", exc_info=True)
            return {"available": False, "state": "UNKNOWN",
                    "reason": "Không đọc được trạng thái detector.", "inputs": []}
        if not isinstance(state, dict):
            state = {}
        raw_decision = state.get("decision")
        decision = raw_decision if isinstance(raw_decision, dict) else {}
        reasons = decision.get("reasons") or state.get("decision_reasons") or []
        return {
            "available": bool(state.get("ai_ok")),
            "state": decision.get("state") or state.get("alarm_state") or state.get("security_state") or "UNKNOWN",
            "reason": decision.get("reason") or state.get("decision_reason")
                      or "Backend chưa cung cấp diễn giải chi tiết cho quyết định hiện tại.",
            "track_ids": state.get("tracked_person_ids", []), "zone": state.get("active_zone"),
            "inputs": reasons if isinstance(reasons, list) else [str(reasons)],
            "timestamp": state.get("last_frame_at"), "source": "Decision Engine / detector status",
            "inference": "Không tự suy diễn nguyên nhân khi backend không cung cấp dữ liệu.",
        }

    return router
