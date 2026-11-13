"""Device heartbeat and RFID scan compatibility/status routes."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from ..schemas import DeviceHeartbeat
from ..services.device_read_service import DeviceReadService


def create_device_router(services: Any) -> APIRouter:
    router = APIRouter()
    read_service = DeviceReadService(
        db_session=services.db_session,
        mask_uid=services.mask_uid,
        mask_uid_payload=services.mask_uid_payload,
    )

    @router.post("/api/device/heartbeat", dependencies=[Depends(services.require_device_key)])
    def device_heartbeat(payload: DeviceHeartbeat) -> dict[str, Any]:
        with services.db_session() as db:
            db.execute(
                """INSERT INTO device_heartbeats(device_id,last_seen,alarm) VALUES(?,?,?)
                   ON CONFLICT(device_id) DO UPDATE SET last_seen=excluded.last_seen,alarm=excluded.alarm""",
                (payload.device_id, services.now_business(), services.current_alarm_level()),
            )
        return {
            "alarm": services.current_alarm_level(),
            "siren": bool(services.incident_status().get("siren", False)),
        }

    @router.get("/api/scans", dependencies=[Depends(services.require_session)])
    def list_scans_compat(request: Request, limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
        """Compatibility response for the selected KHO.DOAN2 web UI."""
        return read_service.list_scans(
            limit, getattr(request.state, "khoai_role", None) == "admin"
        )

    @router.get("/api/rfid/last-unknown", dependencies=[Depends(services.require_session)])
    def last_unknown_card(request: Request) -> dict[str, Any]:
        return read_service.last_unknown_card(
            getattr(request.state, "khoai_role", None) == "admin"
        )

    return router
