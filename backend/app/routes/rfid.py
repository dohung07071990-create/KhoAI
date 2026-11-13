"""RFID scan endpoint and camera-ticket issuance."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ..schemas import AccessCheck, RFIDScan


def create_rfid_router(services: Any) -> APIRouter:
    router = APIRouter()

    @router.post("/api/rfid/scan", dependencies=[Depends(services.require_device_key)])
    def rfid_scan(payload: RFIDScan, request: Request) -> dict[str, Any]:
        header_device_id = request.headers.get("x-device-id")
        if header_device_id and header_device_id.strip() != payload.device_id:
            raise HTTPException(status_code=400, detail="X-Device-ID phải trùng với device_id trong yêu cầu.")
        result = services.check_rfid_access(AccessCheck(uid=payload.uid), payload.device_id)
        ticket = None
        camera_permission = False
        camera_message = None
        if result["allowed"] and not result.get("deduplicated"):
            uid = services.normalize_uid(payload.uid)
            with services.db_session() as db:
                zones = [row["zone"] for row in db.execute(
                    "SELECT zone FROM card_permissions WHERE uid=?", (uid,)
                ).fetchall()]
            try:
                detector_module = services.detector_module_provider()
                detector = detector_module.detector
                camera_zone_id = str(getattr(detector_module, "CAMERA_ZONE_ID", "external_usb_zone"))
                camera_permission = camera_zone_id in zones
                if camera_permission:
                    ticket_seconds = float(getattr(detector_module, "RFID_TICKET_SECONDS", 20.0))
                    created_ticket = detector.create_rfid_ticket(
                        uid, result.get("name"), zones, ttl_seconds=ticket_seconds
                    )
                    if created_ticket.get("capacity_reached"):
                        camera_message = "Hàng đợi vé camera đang đầy; thẻ được xác thực nhưng chưa tạo vé liên kết Track."
                    else:
                        ticket = created_ticket
                else:
                    camera_message = "Thẻ chưa có quyền Camera USB ngoài."
                    with services.db_session() as db:
                        db.execute(
                            """INSERT INTO security_events(event_at,event_type,track_id,severity,message,details_json)
                               VALUES(?,?,?,?,?,?)""",
                            (services.now_business(), "rfid_camera_permission_missing", None, "warning",
                             camera_message,
                             json.dumps({"uid": uid, "camera_zone": camera_zone_id}, ensure_ascii=False)),
                        )
            except Exception:
                services.logger.exception("Không xử lý được quyền camera/ticket cho UID %s", uid)
                ticket = None
                camera_permission = False
                camera_message = "Camera AI hoặc hệ thống cấp vé hiện không khả dụng; không tạo vé camera."
        elif result.get("deduplicated"):
            camera_message = "Quẹt trùng trong thời gian chống lặp; không trừ quota hoặc tạo vé lần nữa."
        return {
            # A duplicate must not trigger the physical actuator a second time.
            "allow": result["allowed"] and not result.get("deduplicated"),
            "reason": "duplicate_scan" if result.get("deduplicated") else result.get("reason"),
            "name": result.get("name"), "ticket": ticket,
            "deduplicated": bool(result.get("deduplicated")),
            "camera_permission": camera_permission, "camera_message": camera_message,
            "message": camera_message or ("Cho phép" if result["allowed"] else "Từ chối"),
            "alarm": services.current_alarm_level(),
            "siren": bool(services.incident_status().get("siren", False)),
        }

    return router
